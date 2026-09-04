"""Per-claim extraction + truthfulness binding for the nodal claim tree.

Turns a real answer into a scored claim DAG (the input to ``claim_scoring``). Two stages:

1. **Extract** — decompose the answer into atomic claims, each tagged ``anchored`` (a fact meant to
   be grounded in a source), ``derived`` (a conclusion inferred from other claims, with reasoning
   steps + parent links), or ``orphan`` (a floating aside). Two interchangeable backends fill the
   same slot, exactly like the scorers:
     * ``StubClaimExtractor`` — deterministic, offline, no model (content-word heuristics).
     * ``LlmClaimExtractor``  — one Claude/Groq JSON call; injectable client, temperature 0, fail-closed.

2. **Bind** — for each claim, compute the three truthfulness sub-scores **against the source
   context** and (for derived claims) the reasoning fidelity, then hand the assembled
   :class:`~aah.api.claim_scoring.ClaimNode` set to ``score_tree``. The grounding check is per-claim
   entailment of the claim against the provided source documents — deterministic overlap offline, or
   an injected NLI callable (``ClaudeNLIScorer``) live.

Everything is additive; nothing here touches the frozen contracts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional, Sequence

from .claim_scoring import ClaimNode, ParentLink, score_tree

# reasoning connectives that split a sentence into premise -> conclusion.
# forward:  <premise> CONN <conclusion>   (the conclusion is derived FROM the premise)
_FWD_RE = re.compile(
    r"\b(therefore|thus|hence|consequently|as a result|which means|means that|"
    r"implies|implying|leading to|so)\b", re.I)
# backward: <conclusion> CONN <premise>   (the premise justifies the conclusion)
_BWD_RE = re.compile(r"\b(because|since|due to|driven by|owing to|as a consequence of)\b", re.I)
# coordinate separators that string independent clauses into one sentence -> split into atomic facts.
# bare commas are deliberately NOT separators (they would shred "1,200" and plain noun lists).
_COORD_RE = re.compile(
    r"\s*;\s*|\s*,?\s+and\s+|\s*,?\s+but\s+|\s*,?\s+while\s+|\s*,?\s+whereas\s+", re.I)
# opinion/sentiment markers -> a subjective aside is an orphan, not a groundable fact, even when it
# carries a proper noun (e.g. "The CEO seemed optimistic").
_SUBJECTIVE = frozenset((
    "seemed", "seems", "appears", "appeared", "felt", "feels", "nice", "optimistic", "pessimistic",
    "impressive", "exciting", "excited", "happy", "unfortunate", "unfortunately", "interesting",
    "great", "wonderful", "remarkable", "encouraging", "disappointing", "lovely", "amazing", "hopeful",
))
_SUPPORT_SCORE = {"strong": 0.9, "partial": 0.6, "weak": 0.4, "not_evaluable": 0.3, "": 0.5}
# common words filtered from the overlap proxy so function words don't inflate grounding
_STOP = frozenset((
    "the", "and", "was", "were", "for", "with", "that", "this", "from", "has", "have", "are",
    "its", "our", "their", "but", "not", "all", "any", "been", "over", "into", "than", "then",
    "they", "you", "your", "his", "her", "had", "will", "would", "which", "who", "what", "when",
    "there", "here", "also", "more", "most", "some", "such", "very", "can", "could", "may",
))


# --- extraction data model ----------------------------------------------------------
@dataclass
class ClaimParent:
    parent_id: str
    load_bearing: bool = True
    or_group: Optional[str] = None
    relation: str = ""          # short natural-language description of the link (e.g. "because revenue rose")


@dataclass
class ExtractedClaim:
    id: str
    text: str
    kind: str = "anchored"                        # anchored | derived | orphan
    parents: list[ClaimParent] = field(default_factory=list)
    reasoning_steps: list[str] = field(default_factory=list)


def _content_words(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", (s or "").lower()) if len(w) > 2 and w not in _STOP}


def _overlap(a: str, b: str) -> float:
    """Fraction of a's content words present in b (0..1). The deterministic grounding proxy."""
    aw = _content_words(a)
    if not aw:
        return 0.0
    return round(len(aw & _content_words(b)) / len(aw), 4)


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", (text or "").strip())
    return [p.strip() for p in parts if len(p.strip()) > 3]


def _has_salient(text: str) -> bool:
    """A factual assertion usually carries a number or a proper noun; a throwaway aside doesn't.
    Used so the stub doesn't mistake a paraphrased fact for an orphan just because it overlaps the
    sources lexically-poorly."""
    if re.search(r"\d", text):
        return True
    words = text.split()
    return any(w[:1].isupper() for w in words[1:])       # a capitalized word after the first


# --- clause atomizer ----------------------------------------------------------------
def _is_subjective(text: str) -> bool:
    """A clause whose assertion is an opinion/sentiment, not a checkable fact."""
    return bool(_content_words(text) & _SUBJECTIVE)


def _atomize(text: str) -> list[str]:
    """Split one clause into atomic facts on coordinate separators (and/but/while/;), then merge back
    any fragment too thin to stand alone. This splits "$4.2B and margin hit 30%" into two full
    clauses while keeping noun pairs like "research and development" together."""
    text = (text or "").strip(" ,.;:")
    if not text:
        return []
    parts = [p.strip(" ,.;:") for p in _COORD_RE.split(text)]
    parts = [p for p in parts if p]
    merged: list[str] = []
    for p in parts:
        if merged and (len(_content_words(p)) < 2 or len(_content_words(merged[-1])) < 2):
            merged[-1] = f"{merged[-1]} and {p}"          # rejoin a fragment that can't stand alone
        else:
            merged.append(p)
    return merged or [text]


def _reasoning_split(sent: str) -> Optional[tuple[str, str]]:
    """Split a sentence at its first reasoning connective into (premise, conclusion), where the
    conclusion is a *derived* claim justified by the premise. Returns None if no connective yields a
    contentful conclusion."""
    fwd, bwd = _FWD_RE.search(sent), _BWD_RE.search(sent)
    if fwd and bwd:
        m, forward = (fwd, True) if fwd.start() <= bwd.start() else (bwd, False)
    elif fwd:
        m, forward = fwd, True
    elif bwd:
        m, forward = bwd, False
    else:
        return None
    left, right = sent[:m.start()].strip(" ,.;:"), sent[m.end():].strip(" ,.;:")
    premise, conclusion = (left, right) if forward else (right, left)
    if len(_content_words(conclusion)) < 2:
        return None
    return premise, conclusion


# --- extractors ---------------------------------------------------------------------
class StubClaimExtractor:
    """Deterministic, model-free extraction: atomic-clause splitting + connective/overlap heuristics.

    Each sentence is first split at a reasoning connective into a **premise** (anchored fact) and a
    **conclusion** (a ``derived`` claim whose load-bearing parents are the recent anchored facts).
    Each side is then atomized on coordinate separators so "A and B" become two independent claims. A
    subjective aside is an ``orphan``; a fact overlapping neither the question nor the context is an
    ``orphan``; everything else is ``anchored``. A ``derived`` clause with no available parent falls
    back to a plain fact — never a dangling derived node. Good enough to exercise the pipeline offline.
    """

    async def extract(self, question: str, response: str, context: str) -> list[ExtractedClaim]:
        claims: list[ExtractedClaim] = []
        anchored_ids: list[str] = []
        counter = 0

        def _add_fact(text: str) -> Optional[str]:
            nonlocal counter
            text = text.strip(" ,.;:")
            if len(_content_words(text)) < 2:
                return None                               # too thin to be a claim
            cid = f"c{counter}"
            counter += 1
            if _is_subjective(text) and not _citations(text):
                kind = "orphan"                           # opinion/sentiment aside
            elif (_citations(text) or _has_salient(text)
                  or _overlap(text, context) >= 0.2 or _overlap(text, question) >= 0.2):
                kind = "anchored"                         # a fact meant to be grounded
            else:
                kind = "orphan"                           # floating, off-topic aside
            claims.append(ExtractedClaim(cid, text, kind))
            if kind == "anchored":
                anchored_ids.append(cid)
            return cid

        for sent in _split_sentences(response):
            split = _reasoning_split(sent)
            if split:
                premise, conclusion = split
                for part in _atomize(premise):
                    _add_fact(part)                       # premise clause(s) -> anchored facts
                parents = [ClaimParent(pid) for pid in anchored_ids[-2:]]   # lean on the last facts
                ctext = conclusion.strip(" ,.;:")
                if parents and len(_content_words(ctext)) >= 2:
                    claims.append(ExtractedClaim(f"c{counter}", ctext, "derived", parents,
                                                 _atomize(conclusion) or [ctext]))
                    counter += 1
                else:
                    for part in _atomize(ctext):          # no parent -> plain facts, never a dangling
                        _add_fact(part)                    # derived node (and still atomically split)
            else:
                for part in _atomize(sent):
                    _add_fact(part)
        return claims


_EXTRACT_SYSTEM = (
    "You decompose an ANSWER into ATOMIC claims for a truthfulness audit. Return ONLY a JSON array; "
    "each element: {\"id\": \"c0\", \"text\": \"...\", \"kind\": \"anchored|derived|orphan\", "
    "\"parents\": [{\"id\": \"c1\", \"load_bearing\": true, \"or_group\": null, \"relation\": \"...\"}], "
    "\"reasoning_steps\": [\"...\"]}. "
    "ATOMICITY (critical): each claim must state EXACTLY ONE checkable assertion — one subject, one "
    "predicate, one value. Split any sentence joining multiple facts (and/but/;/that also) into "
    "separate claims. A claim must be able to stand alone as a single true/false check. "
    "DESCRIPTIVE & SELF-CONTAINED: resolve pronouns and shorthand so each claim is understandable on "
    "its own (write 'Acme's Q3 revenue was $4.2B', not 'it rose 12%'); do not merge two facts to save "
    "words. "
    "anchored = a factual assertion meant to be grounded directly in a source (a BASE claim). "
    "derived = a conclusion inferred from other claims. List every premise in parents. Set "
    "load_bearing=true for a premise the conclusion NEEDS (an AND term), false for merely supporting "
    "context; give the SAME or_group id to interchangeable alternatives (an OR term). For each parent "
    "add a short 'relation' phrase describing the link (e.g. 'because revenue rose', 'assuming demand "
    "holds'). Build these relationships freely — a rich parent/child tree is expected. "
    "orphan = a floating aside (subjective, or grounded in neither a source nor other claims). "
    "Keep ids stable and reference a parent only after it is defined where possible."
)


class LlmClaimExtractor:
    """One JSON call to decompose the answer into a claim DAG. Client is injectable for offline tests."""

    def __init__(self, client: Any = None, model: str = "claude-opus-4-8"):
        self._client = client
        self._model = model

    def _get_client(self) -> Any:
        if self._client is None:
            import anthropic
            self._client = anthropic.AsyncAnthropic()
        return self._client

    async def extract(self, question: str, response: str, context: str) -> list[ExtractedClaim]:
        client = self._get_client()
        msg = await client.messages.create(
            model=self._model, max_tokens=2048, system=_EXTRACT_SYSTEM,
            messages=[{"role": "user", "content":
                       f"QUESTION:\n{question}\n\nANSWER (decompose this):\n{response}"}],
        )
        from ..layer_a.scorers.base import extract_text
        return _coerce_claims(_loads_array(extract_text(msg)))


def _loads_array(text: str) -> list:
    import json
    m = re.search(r"\[.*\]", text or "", re.DOTALL)
    if not m:
        return []
    try:
        obj = json.loads(m.group(0))
        return obj if isinstance(obj, list) else []
    except ValueError:
        return []


def _coerce_claims(data: Any) -> list[ExtractedClaim]:
    out: list[ExtractedClaim] = []
    for i, c in enumerate(data or []):
        if not isinstance(c, dict):
            continue
        parents = [
            ClaimParent(str(p.get("id")), bool(p.get("load_bearing", True)), p.get("or_group"),
                        str(p.get("relation") or ""))
            for p in (c.get("parents") or []) if isinstance(p, dict) and p.get("id")
        ]
        out.append(ExtractedClaim(
            id=str(c.get("id") or f"c{i}"), text=str(c.get("text") or "").strip(),
            kind=(c.get("kind") if c.get("kind") in ("anchored", "derived", "orphan") else "anchored"),
            parents=parents,
            reasoning_steps=[str(s) for s in (c.get("reasoning_steps") or []) if str(s).strip()],
        ))
    return out


# --- truthfulness binding -----------------------------------------------------------
# A scorer maps (claim_text, response, context) -> 0..1. Async so live NLI/judge callables fit.
Scorer = Callable[[str, str, str], Awaitable[float]]


async def _det_grounded(claim: str, response: str, context: str) -> float:
    """Deterministic groundedness: how much of the claim is entailed by the source context."""
    return _overlap(claim, context)


async def _det_reasoning(steps: Sequence[str], context: str) -> Optional[float]:
    """Deterministic reasoning fidelity: mean overlap of each step with the context (graded).

    Softer than the entail-count in ``explainability.reasoning_fidelity`` so the offline demo isn't
    all-or-nothing; the live path passes an NLI-backed reasoning scorer instead."""
    steps = [s for s in steps if s.strip()]
    if not steps:
        return None
    return round(sum(_overlap(s, context) for s in steps) / len(steps), 4)


def _quality_from_evidence(claim: str, evidence: Sequence[dict]) -> float:
    """Deterministic source quality: best support level among sources that overlap the claim."""
    if not evidence:
        return 0.75
    best = 0.0
    for e in evidence:
        text = " ".join(str(e.get(k) or "") for k in ("title", "quote", "domain"))
        if _overlap(claim, text) > 0.1 or _overlap(text, claim) > 0.1:
            best = max(best, _SUPPORT_SCORE.get((e.get("support") or "").lower(), 0.5))
    return round(best or 0.4, 4)      # a claim matching no source has thin quality


# --- source attribution: are the claim's cited sources actually in the provided set? -----------
_CITE_RES = [re.compile(p, re.I) for p in (
    r"according to\s+([^.,;:()\[\]]+)",
    r"\bper\s+(?:the\s+)?([^.,;:()\[\]]+)",
    r"based on\s+([^.,;:()\[\]]+)",
    r"cited in\s+([^.,;:()\[\]]+)",
    r"reported by\s+([^.,;:()\[\]]+)",
    r"source:\s*([^.,;:()\[\]]+)",
    r"\bthe\s+([A-Za-z0-9\-' ]+?(?:filing|report|article|statement|press release|"
    r"earnings (?:call|report)|10-?[kq]|8-?k))\b",
)]
_URL_RE = re.compile(r"https?://\S+", re.I)


def _strip_citations(text: str) -> str:
    """Remove attribution phrases/URLs so grounding judges the FACT, not the 'X said it' clause.
    (Attribution is scored separately against the cited source.)"""
    out = text or ""
    for rx in _CITE_RES:
        out = rx.sub(" ", out)
    out = _URL_RE.sub(" ", out)
    return re.sub(r"\s+", " ", out).strip(" ,.;:")


def _citations(text: str) -> list[str]:
    """Extract explicit source references from a claim (attribution phrases, doc types, URLs)."""
    refs: list[str] = []
    for rx in _CITE_RES:
        for m in rx.finditer(text or ""):
            ref = m.group(1).strip()
            if len(ref) > 2:
                refs.append(ref)
    refs.extend(_URL_RE.findall(text or ""))
    return list(dict.fromkeys(refs))


def _best_evidence_match(ref: str, evidence: Sequence[dict]) -> Optional[dict]:
    """The evidence item a citation ``ref`` refers to (by content-word overlap), or None if the
    cited source is not in the provided set (a fabricated citation)."""
    rw = _content_words(ref)
    if not rw:
        return None
    best, best_ov = None, 0.0
    for ev in evidence:
        ev_text = " ".join(str(ev.get(k) or "") for k in
                           ("title", "domain", "canonicalUrl", "sourceUrl", "url"))
        ew = _content_words(ev_text)
        ov = len(rw & ew) / len(rw) if ew else 0.0
        if ov > best_ov:
            best, best_ov = ev, ov
    return best if best_ov >= 0.34 else None


def _attribution(claim: str, evidence: Sequence[dict]) -> Optional[float]:
    """Citation validity for one claim: every cited source must exist in the provided set.

    Returns 1.0 when all cited sources are present, 0.0 when any citation is fabricated (cites a doc
    not in the set), and None when the claim makes no citation (attribution N/A — not penalized) or
    there is no source set to check against."""
    if not evidence:
        return None
    refs = _citations(claim)
    if not refs:
        return None
    scores = [1.0 if _best_evidence_match(r, evidence) else 0.0 for r in refs]
    return round(min(scores), 4)


async def build_claim_nodes(
    extracted: Sequence[ExtractedClaim], *, response: str, context: str, question: str = "",
    evidence: Optional[Sequence[dict]] = None,
    grounded: Optional[Scorer] = None, attribution: Optional[Scorer] = None,
    reasoning: Optional[Callable[[Sequence[str], str], Awaitable[Optional[float]]]] = None,
) -> dict[str, ClaimNode]:
    """Bind per-claim truthfulness + reasoning scores and return the SCORED ClaimNode tree.

    ``grounded`` defaults to the deterministic overlap proxy; ``reasoning`` to the graded overlap.
    Pass NLI-backed callables for the live/local path. ``source_attribution`` is the deterministic
    citation-validity check against ``evidence`` (an injected ``attribution`` scorer overrides it);
    ``source_quality`` comes from the evidence support levels.
    """
    grounded = grounded or _det_grounded
    reasoning = reasoning or _det_reasoning
    evidence = list(evidence or [])
    nodes: dict[str, ClaimNode] = {}

    for c in extracted:
        node = ClaimNode(id=c.id, text=c.text, kind=c.kind,
                         parents=[ParentLink(p.parent_id, p.load_bearing, p.or_group, p.relation) for p in c.parents])
        if c.kind == "orphan":
            # STUB relevance: how much the floating fact relates to what was ASKED (not the answer
            # it came from). Deliberately thin — the real per-claim relevance judge lands later.
            node.relevance = round(_overlap(c.text, question), 4) if question else 0.3
        else:
            node.groundedness = await grounded(c.text, response, context)
            # source attribution = citation validity (cited sources must be in the set); an injected
            # scorer overrides, else the deterministic citation check. None => N/A (min ignores it).
            node.source_attribution = (await attribution(c.text, response, context)
                                       if attribution is not None else _attribution(c.text, evidence))
            node.source_quality = _quality_from_evidence(c.text, evidence)
            if c.kind == "derived":
                node.reasoning_fidelity = await reasoning(c.reasoning_steps, context)
        nodes[c.id] = node

    return score_tree(nodes)


# --- retrieve-then-verify binding (hybrid retrieval + short-circuit NLI) -------------
async def build_claim_nodes_retrieval(
    extracted: Sequence[ExtractedClaim], *, context: str = "",
    sources: Optional[Sequence[dict]] = None, question: str = "",
    evidence: Optional[Sequence[dict]] = None, entail_fn=None, retriever=None,
    k: int = 8, tau: float = 0.5, cfg: Any = None,
) -> dict[str, ClaimNode]:
    """Bind grounding + attribution via hybrid retrieve-then-verify, then score the tree.

    Grounding = retrieve top-k over ALL sources → NLI best-first with a τ short-circuit. Attribution =
    the same, but scoped to the CITED source (so a real-but-wrong cited source scores low, and a
    fabricated citation → 0). Reasoning fidelity = grounding of a derived claim's steps. Runs the
    (sync, heavy) retrieval+NLI work in a threadpool. ``entail_fn``/``retriever`` are injectable for
    tests; defaults are ``LocalNli.entail_pairs`` + ``HybridRetriever(BM25 + spaCy)``.
    """
    import asyncio as _asyncio

    from .claim_retrieval import (HybridRetriever, InMemoryBM25, Source, SpacyDenseRetriever,
                                  chunk_sources, match_source, to_sources, verify_grounding)

    srcs: list[Source] = to_sources(context, sources)
    evidence = list(evidence or [])
    non_orphan = [c for c in extracted if c.kind != "orphan"]

    if entail_fn is None:
        from .local_nli import get_local_nli
        entail_fn = get_local_nli(cfg).entail_pairs

    # grounding judges the FACT, so strip the citation clause first (attribution scores the source)
    fact = {c.id: (_strip_citations(c.text) or c.text) for c in non_orphan}

    def _work():
        r = retriever
        if r is None:
            r = HybridRetriever(lexical=InMemoryBM25(), dense=SpacyDenseRetriever())
        r.index(chunk_sources(srcs))

        uniq = list({fact[c.id] for c in non_orphan})
        grounded = verify_grounding(uniq, r, entail_fn, k=k, tau=tau) if uniq else {}

        attribution: dict[str, Optional[float]] = {}
        reasoning: dict[str, Optional[float]] = {}
        for c in non_orphan:
            refs = _citations(c.text)
            if not refs or not srcs:
                attribution[c.id] = None
            else:
                per_ref = []
                for ref in refs:
                    sid = match_source(ref, srcs)
                    if sid is None:
                        per_ref.append(0.0)                       # fabricated citation
                    else:                                          # does the CITED source support the fact?
                        res = verify_grounding([fact[c.id]], r, entail_fn, k=k, tau=tau,
                                               source_of={fact[c.id]: sid})
                        per_ref.append(res[fact[c.id]]["score"])
                attribution[c.id] = round(min(per_ref), 4) if per_ref else None
            if c.kind == "derived" and c.reasoning_steps:
                rg = verify_grounding(list(c.reasoning_steps), r, entail_fn, k=k, tau=tau)
                vals = [rg[s]["score"] for s in c.reasoning_steps if s in rg]
                reasoning[c.id] = round(sum(vals) / len(vals), 4) if vals else None
        return grounded, attribution, reasoning

    grounded, attribution, reasoning = await _asyncio.to_thread(_work)

    nodes: dict[str, ClaimNode] = {}
    for c in extracted:
        node = ClaimNode(id=c.id, text=c.text, kind=c.kind,
                         parents=[ParentLink(p.parent_id, p.load_bearing, p.or_group, p.relation) for p in c.parents])
        if c.kind == "orphan":
            node.relevance = round(_overlap(c.text, question), 4) if question else 0.3
        else:
            g = grounded.get(fact[c.id])
            node.groundedness = g["score"] if g else 0.0
            node.source_attribution = attribution.get(c.id)
            node.source_quality = _quality_from_evidence(c.text, evidence)
            if c.kind == "derived":
                node.reasoning_fidelity = reasoning.get(c.id)
        nodes[c.id] = node
    return score_tree(nodes)


# --- live scorer wiring (backend-agnostic: works with any anthropic-shaped async client) ------
def live_scorers(async_client: Any, model: str, *, max_concurrency: int = 2) -> dict:
    """Build NLI-backed ``grounded``/``reasoning`` callables from an async client.

    Reuses ``ClaudeNLIScorer`` (which also drives the Groq/Bedrock paths — the clients quack like
    ``anthropic.AsyncAnthropic``). Grounding is per-claim entailment against the source context;
    reasoning fidelity is the fraction of a derived claim's steps entailed by the context. Calls are
    throttled by a semaphore so free-tier rate limits (HTTP 429) aren't tripped by a burst.

    No ``attribution`` key is returned, so the binder uses its deterministic citation-validity check.
    """
    import asyncio as _asyncio

    from ..contracts import BinaryQuestion, Dimension, EvalMethod, Subtype
    from ..layer_a.scorers.nli import ClaudeNLIScorer

    nli = ClaudeNLIScorer(client=async_client, model=model)
    sem = _asyncio.Semaphore(max_concurrency)

    def _q(text: str) -> BinaryQuestion:
        return BinaryQuestion(id="claim", requirement_id="", dimension=Dimension.FACTUAL_CONSISTENCY,
                              subtype=Subtype.UNSUPPORTED, text=text, violation_example="",
                              eval_method=EvalMethod.NLI)

    async def grounded(claim: str, response: str, context: str) -> float:
        async with sem:
            return float((await nli.score(_q(claim), response, context)).score)

    async def reasoning(steps: Sequence[str], context: str) -> Optional[float]:
        steps = [s for s in steps if s.strip()]
        if not steps:
            return None
        vals = await _asyncio.gather(*[grounded(s, "", context) for s in steps])
        return round(sum(vals) / len(vals), 4)

    return {"grounded": grounded, "reasoning": reasoning}


def local_scorers(cfg: Any = None) -> dict:
    """Build ``grounded``/``reasoning`` from the LOCAL transformer NLI model (no API, no rate limit).

    This is the design-intended grounding path (dedicated NLI, not an LLM judge): each claim is
    entailed-checked against the source context, graded 0..1. Attribution falls to the binder's
    deterministic citation-validity check. Pair with :func:`prewarm_grounding` for batched speed.
    """
    import asyncio as _asyncio

    from .local_nli import grounding_scorer

    grounded = grounding_scorer(cfg)

    async def reasoning(steps: Sequence[str], context: str) -> Optional[float]:
        steps = [s for s in steps if s.strip()]
        if not steps:
            return None
        vals = await _asyncio.gather(*[grounded(s, "", context) for s in steps])
        return round(sum(vals) / len(vals), 4)

    return {"grounded": grounded, "reasoning": reasoning}


async def prewarm_grounding(claims: Sequence[ExtractedClaim], context: str, cfg: Any = None) -> None:
    """Batch-score every claim (and every derived claim's reasoning steps) against the context up
    front, filling the local-NLI cache so the subsequent per-claim binding calls are cache hits."""
    from .local_nli import prewarm

    texts: list[str] = []
    for c in claims:
        if c.kind != "orphan":
            texts.append(c.text)
        texts.extend(c.reasoning_steps)
    if texts:
        await prewarm(texts, context, cfg)


async def extract_and_score(
    question: str, response: str, context: str, *,
    extractor: Any = None, evidence: Optional[Sequence[dict]] = None,
    grounded: Optional[Scorer] = None, attribution: Optional[Scorer] = None,
    reasoning: Optional[Callable[[Sequence[str], str], Awaitable[Optional[float]]]] = None,
) -> dict[str, ClaimNode]:
    """End-to-end: extract claims from the answer, bind truthfulness, and score the tree."""
    extractor = extractor or StubClaimExtractor()
    claims = await extractor.extract(question, response, context)
    return await build_claim_nodes(claims, response=response, context=context, question=question,
                                   evidence=evidence, grounded=grounded, attribution=attribution,
                                   reasoning=reasoning)
