"""Tests for the retrieve-then-verify layer (aah/api/claim_retrieval.py).

No spaCy / NLI model needed: dense retrieval and NLI are faked so the retrieval, fusion, source
scoping, and short-circuit logic are verified deterministically.
"""

from __future__ import annotations

from aah.api.claim_retrieval import (
    Chunk, HybridRetriever, InMemoryBM25, Retriever, Source, chunk_sources,
    match_source, to_sources, verify_grounding,
)


def _chunks(*pairs) -> list[Chunk]:
    return [Chunk(id=f"c{i}", source_id=s, text=t) for i, (s, t) in enumerate(pairs)]


# --- chunking -----------------------------------------------------------------------
def test_chunk_sources_tags_source_and_overlaps():
    src = Source(id="A", text=" ".join(f"w{i}" for i in range(400)))
    chunks = chunk_sources([src], words=160, overlap=40)
    assert len(chunks) >= 3
    assert all(c.source_id == "A" for c in chunks)
    # consecutive windows overlap (last words of chunk0 reappear in chunk1)
    assert set(chunks[0].text.split()[-40:]) & set(chunks[1].text.split())


def test_to_sources_accepts_blob_or_per_source():
    assert to_sources(context="hello world")[0].id == "context"
    srcs = to_sources(sources=[{"id": "a", "text": "x", "title": "T"}])
    assert srcs[0].id == "a" and srcs[0].title == "T"
    assert to_sources(context="") == []


# --- BM25 inverted index ------------------------------------------------------------
def test_bm25_ranks_term_matches_and_skips_unrelated():
    idx = InMemoryBM25()
    idx.index(_chunks(("A", "revenue was 4.2 billion dollars"),
                      ("A", "cloud gross margin rose"),
                      ("B", "the company mascot is a penguin")))
    res = idx.search("revenue billion", k=3)
    assert res and "revenue" in res[0].text
    assert all("penguin" not in c.text for c in res)     # no shared term -> never surfaced


def test_bm25_source_filter_scopes_results():
    idx = InMemoryBM25()
    idx.index(_chunks(("A", "revenue rose sharply"), ("B", "revenue fell sharply")))
    res = idx.search("revenue", k=5, source_id="B")
    assert len(res) == 1 and res[0].source_id == "B"


# --- hybrid fusion ------------------------------------------------------------------
class _FakeDense(Retriever):
    """Returns any chunk whose text contains 'PARA' — stands in for a semantic/paraphrase hit."""

    def index(self, chunks):
        self._ch = list(chunks)

    def search(self, query, k, *, source_id=None):
        return [c for c in self._ch if "PARA" in c.text and (source_id is None or c.source_id == source_id)][:k]


def test_hybrid_union_recovers_a_dense_only_hit():
    lex = InMemoryBM25()
    hy = HybridRetriever(lexical=lex, dense=_FakeDense())
    # c0 shares no terms with the claim (BM25 misses it) but the fake dense retrieves it via 'PARA'
    hy.index(_chunks(("A", "PARA earnings climbed steeply"),
                     ("A", "revenue was 4.2 billion dollars")))
    ids = {c.id for c in hy.search("revenue 4.2 billion", k=5)}
    assert "c1" in ids       # lexical hit
    assert "c0" in ids       # dense-only hit — union protected recall


# --- short-circuit verifier ---------------------------------------------------------
def test_verify_short_circuits_and_batches_across_claims():
    idx = InMemoryBM25()
    idx.index(_chunks(("A", "revenue was 4.2 billion"), ("A", "cloud margin rose"),
                      ("A", "an inquiry was opened")))
    calls = {"pairs": 0}

    def entail_fn(pairs):
        calls["pairs"] += len(pairs)
        # 'grounded' iff the claim's first word appears in the candidate chunk
        return [1.0 if p.split() and p.split()[0] and (h.split()[0] in p) else 0.0 for p, h in pairs]

    out = verify_grounding(["revenue x", "inquiry y"], idx, entail_fn, k=3, tau=0.5)
    assert out["revenue x"]["grounded"] and out["revenue x"]["source_id"] == "A"
    assert out["inquiry y"]["grounded"]
    # short-circuit: each claim resolves on its first good candidate, so far fewer than 2*k pairs
    assert calls["pairs"] <= 4


def test_verify_reports_max_when_never_reaching_tau():
    idx = InMemoryBM25()
    idx.index(_chunks(("A", "revenue was 4.2 billion")))

    def entail_fn(pairs):
        return [0.3 for _ in pairs]          # always below tau

    out = verify_grounding(["revenue"], idx, entail_fn, k=3, tau=0.5)
    assert out["revenue"]["grounded"] is False
    assert out["revenue"]["score"] == 0.3    # max seen, still graded


def test_verify_source_scoping_for_attribution():
    idx = InMemoryBM25()
    idx.index(_chunks(("filing", "revenue was 4.2 billion"), ("news", "revenue was 4.2 billion")))

    def entail_fn(pairs):
        return [1.0 for _ in pairs]

    # scope the claim's retrieval to source 'filing' only
    out = verify_grounding(["revenue"], idx, entail_fn, k=3, tau=0.5, source_of={"revenue": "filing"})
    assert out["revenue"]["source_id"] == "filing"


# --- citation -> source matching ----------------------------------------------------
def test_match_source_maps_reference_to_source_id():
    sources = [Source(id="s1", text="", title="Q3 filing"), Source(id="s2", text="", title="Newswire report")]
    assert match_source("the Q3 filing", sources) == "s1"
    assert match_source("the Bloomberg terminal", sources) is None
