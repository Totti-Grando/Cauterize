"""Retrieve-then-verify: a per-source inverted-index retriever that narrows the corpus to the
top-k candidate chunks for a claim BEFORE the (expensive) NLI runs.

Why: NLI models have a ~512-token window, so a real corpus chunks into hundreds of windows. Scoring
every claim against every window is O(claims × corpus). An **inverted index** avoids that — a query
only touches the chunks that share a term with the claim, never the whole corpus. The retriever needs
only good *recall* (get the supporting chunk into the top-k); the NLI does the precise judging.

Backends behind one interface (:class:`Retriever`):

* :class:`InMemoryBM25` — pure-Python BM25 over an in-memory inverted index. **Zero dependencies, no
  database, no HuggingFace** — the portable default; runs identically on any machine.
* Postgres / SQLite-FTS5 backends slot in here for persistence/scale (Postgres uses a GIN
  ``tsvector`` index; both are inverted indexes too). See :class:`Retriever` for the contract.

Two scopes come free from the per-source index: grounding retrieves over **all** sources ("supported
anywhere?"); attribution retrieves within the **cited** source only ("supported by the one you named?").
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Optional, Sequence

# keep numbers / tickers / doc-codes (4.2, 68, q3, 10-k) — they carry the signal in financial claims
_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9.\-]*")
_STOP = frozenset((
    "the", "and", "was", "were", "for", "with", "that", "this", "from", "has", "have", "are",
    "its", "our", "their", "but", "not", "all", "any", "been", "over", "into", "than", "then",
    "they", "you", "your", "his", "her", "had", "will", "would", "which", "who", "what", "when",
    "there", "here", "also", "more", "most", "some", "such", "very", "can", "could", "may", "per",
    "according", "based",
))


def _tokens(text: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall((text or "").lower()) if len(t) >= 2 and t not in _STOP]


@dataclass
class Chunk:
    id: str
    source_id: str
    text: str


@dataclass
class Source:
    id: str
    text: str
    title: str = ""


def chunk_sources(sources: Sequence[Source], *, words: int = 160, overlap: int = 40) -> list[Chunk]:
    """Split each source into overlapping word windows, each tagged with its ``source_id``."""
    step = max(1, words - overlap)
    chunks: list[Chunk] = []
    for src in sources:
        toks = (src.text or "").split()
        if not toks:
            continue
        made = 0
        for start in range(0, len(toks), step):
            piece = toks[start:start + words]
            if not piece:
                break
            chunks.append(Chunk(id=f"{src.id}#{made}", source_id=src.id, text=" ".join(piece)))
            made += 1
            if start + words >= len(toks):
                break
    return chunks


def to_sources(context: str = "", sources: Optional[Sequence[dict]] = None) -> list[Source]:
    """Normalize input into per-source records. Accepts an explicit per-source list
    (``{id/source_id, text, title}``) or a single ``context`` blob (one synthetic source)."""
    if sources:
        out: list[Source] = []
        for i, s in enumerate(sources):
            sid = str(s.get("id") or s.get("source_id") or f"src{i}")
            out.append(Source(id=sid, text=str(s.get("text") or ""), title=str(s.get("title") or "")))
        return out
    return [Source(id="context", text=context or "")] if (context or "").strip() else []


# --- retriever interface ------------------------------------------------------------
class Retriever:
    """Contract for a chunk retriever. Implementations own an inverted index so ``search`` never
    scans the whole corpus. A Postgres backend implements the same two methods over a GIN tsvector
    index; a SQLite-FTS5 backend over an FTS5 table."""

    def index(self, chunks: Sequence[Chunk]) -> None:
        raise NotImplementedError

    def search(self, query: str, k: int, *, source_id: Optional[str] = None) -> list[Chunk]:
        raise NotImplementedError


class InMemoryBM25(Retriever):
    """Pure-Python BM25 over an in-memory inverted index. No DB, no deps, no HuggingFace.

    ``search`` unions the postings of the query's terms, so only chunks that share a term with the
    claim are ever scored — the corpus is never fully scanned. ``source_id`` restricts scoring to one
    source's chunks (the attribution scope)."""

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self._chunks: dict[str, Chunk] = {}
        self._postings: dict[str, dict[str, int]] = defaultdict(dict)   # term -> {chunk_id: tf}
        self._len: dict[str, int] = {}                                  # chunk_id -> token count
        self._df: dict[str, int] = defaultdict(int)                     # term -> doc frequency
        self._by_source: dict[str, set[str]] = defaultdict(set)         # source_id -> {chunk_id}
        self._n = 0
        self._avgdl = 0.0

    def index(self, chunks: Sequence[Chunk]) -> None:
        for c in chunks:
            toks = _tokens(c.text)
            if not toks:
                continue
            self._chunks[c.id] = c
            self._len[c.id] = len(toks)
            self._by_source[c.source_id].add(c.id)
            for term, tf in Counter(toks).items():
                self._postings[term][c.id] = tf
                self._df[term] += 1
        self._n = len(self._chunks)
        self._avgdl = (sum(self._len.values()) / self._n) if self._n else 0.0

    def _idf(self, term: str) -> float:
        df = self._df.get(term, 0)
        return math.log(1 + (self._n - df + 0.5) / (df + 0.5))

    def search(self, query: str, k: int, *, source_id: Optional[str] = None) -> list[Chunk]:
        allowed = self._by_source.get(source_id) if source_id else None
        scores: dict[str, float] = defaultdict(float)
        for term in set(_tokens(query)):
            posting = self._postings.get(term)
            if not posting:
                continue
            idf = self._idf(term)
            for cid, tf in posting.items():                 # only chunks containing this term
                if allowed is not None and cid not in allowed:
                    continue
                dl = self._len[cid]
                denom = tf + self.k1 * (1 - self.b + self.b * dl / (self._avgdl or 1))
                scores[cid] += idf * (tf * (self.k1 + 1)) / denom
        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:k]
        return [self._chunks[cid] for cid, _ in ranked]


class SpacyDenseRetriever(Retriever):
    """Dense (semantic) retrieval via spaCy static word vectors — catches paraphrase where BM25's
    exact-term match fails. HuggingFace-free: ``en_core_web_lg`` downloads from spaCy's own CDN (or
    transfer the installed model package). A chunk/query vector is the L2-normalized mean word vector,
    so cosine similarity is a dot product. Lazy-loaded; parser/NER/tagger disabled for speed."""

    def __init__(self, model: str = "en_core_web_lg"):
        self._model = model
        self._nlp = None
        self._chunks: dict[str, Chunk] = {}
        self._vecs: dict[str, "any"] = {}
        self._by_source: dict[str, list[str]] = defaultdict(list)

    def _load(self):
        if self._nlp is None:
            import spacy
            self._nlp = spacy.load(
                self._model,
                disable=["parser", "ner", "tagger", "lemmatizer", "attribute_ruler", "senter"],
            )
        return self._nlp

    def _embed(self, texts: Sequence[str]):
        import numpy as np
        nlp = self._load()
        out = []
        for doc in nlp.pipe(list(texts), batch_size=64):
            v = np.asarray(doc.vector, dtype="float32")
            n = float(np.linalg.norm(v))
            out.append(v / n if n > 0 else v)
        return out

    def index(self, chunks: Sequence[Chunk]) -> None:
        chunks = [c for c in chunks if c.text.strip()]
        for c, v in zip(chunks, self._embed([c.text for c in chunks])):
            self._chunks[c.id] = c
            self._vecs[c.id] = v
            self._by_source[c.source_id].append(c.id)

    def search(self, query: str, k: int, *, source_id: Optional[str] = None) -> list[Chunk]:
        import numpy as np
        if not self._vecs:
            return []
        qv = self._embed([query])[0]
        ids = self._by_source.get(source_id, []) if source_id else list(self._vecs.keys())
        scored = [(cid, float(np.dot(qv, self._vecs[cid]))) for cid in ids]
        scored.sort(key=lambda kv: kv[1], reverse=True)
        return [self._chunks[cid] for cid, _ in scored[:k]]


class HybridRetriever(Retriever):
    """BM25 (lexical) ∪ dense (semantic), fused by reciprocal-rank fusion.

    Union protects recall — BM25 nails exact entities/numbers, dense catches paraphrase — and RRF
    gives one combined ordering without tuning score scales. The dense half is optional: with no dense
    retriever this degrades to pure BM25."""

    def __init__(self, lexical: Optional[Retriever] = None, dense: Optional[Retriever] = None,
                 *, rrf_k: int = 60, pool: int = 10):
        self.lexical = lexical or InMemoryBM25()
        self.dense = dense
        self.rrf_k = rrf_k
        self.pool = pool                      # per-retriever candidate pool before fusion

    def index(self, chunks: Sequence[Chunk]) -> None:
        self.lexical.index(chunks)
        if self.dense is not None:
            self.dense.index(chunks)

    def search(self, query: str, k: int, *, source_id: Optional[str] = None) -> list[Chunk]:
        n = max(k, self.pool)
        runs = [self.lexical.search(query, n, source_id=source_id)]
        if self.dense is not None:
            runs.append(self.dense.search(query, n, source_id=source_id))
        fused: dict[str, float] = defaultdict(float)
        objs: dict[str, Chunk] = {}
        for run in runs:
            for rank, c in enumerate(run):
                fused[c.id] += 1.0 / (self.rrf_k + rank + 1)     # reciprocal-rank fusion
                objs[c.id] = c
        ranked = sorted(fused.items(), key=lambda kv: kv[1], reverse=True)[:k]
        return [objs[cid] for cid, _ in ranked]


# --- retrieve-then-verify with rank-parallel short-circuit --------------------------
def verify_grounding(
    claims: Sequence[str], retriever: Retriever, entail_fn, *,
    k: int = 8, tau: float = 0.5, source_of: Optional[dict] = None,
) -> dict[str, dict]:
    """Ground many claims: retrieve top-k candidates each, then NLI best-first with a short-circuit,
    batched **across claims** at each rank so the NLI stays efficient.

    ``entail_fn(pairs)`` scores ``(premise_chunk_text, claim)`` pairs -> entailment probs (e.g.
    ``LocalNli.entail_pairs``). ``tau`` is the entailment threshold to declare grounded and STOP for
    that claim. ``source_of`` maps a claim to a source id to scope retrieval to that one source (the
    attribution scope); omit for grounding over all sources.

    Returns ``{claim: {score, grounded, chunk_id, source_id}}`` where ``score`` is the entailment at
    short-circuit (or the max seen if none reached ``tau``).
    """
    cands: dict[str, list[Chunk]] = {}
    for c in claims:
        sid = source_of.get(c) if source_of else None
        cands[c] = retriever.search(c, k, source_id=sid)

    best: dict[str, tuple[float, Optional[Chunk]]] = {c: (0.0, None) for c in claims}
    grounded: dict[str, tuple[float, Chunk]] = {}
    active = [c for c in claims if cands[c]]
    max_depth = max((len(v) for v in cands.values()), default=0)

    for depth in range(max_depth):
        pairs, owners = [], []
        for c in active:
            if depth < len(cands[c]):
                pairs.append((cands[c][depth].text, c))       # (premise=chunk, hypothesis=claim)
                owners.append(c)
        if not pairs:
            break
        for c, p in zip(owners, entail_fn(pairs)):            # one batched NLI call per rank
            if p > best[c][0]:
                best[c] = (p, cands[c][depth])
            if p >= tau and c not in grounded:
                grounded[c] = (p, cands[c][depth])            # short-circuit this claim
        active = [c for c in active if c not in grounded and depth + 1 < len(cands[c])]
        if not active:
            break

    out: dict[str, dict] = {}
    for c in claims:
        p, ch = grounded[c] if c in grounded else best[c]
        out[c] = {"score": round(float(p), 4), "grounded": bool(p >= tau),
                  "chunk_id": ch.id if ch else None, "source_id": ch.source_id if ch else None}
    return out


# --- source matching for attribution scope ------------------------------------------
def match_source(ref: str, sources: Sequence[Source]) -> Optional[str]:
    """Map a citation reference (e.g. 'the Q3 filing') to a source id by title/id token overlap."""
    rw = set(_tokens(ref))
    if not rw:
        return None
    best, best_ov = None, 0.0
    for s in sources:
        sw = set(_tokens(f"{s.title} {s.id}"))
        ov = (len(rw & sw) / len(rw)) if sw else 0.0
        if ov > best_ov:
            best, best_ov = s.id, ov
    return best if best_ov >= 0.34 else None
