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

# reasoning connectives that mark a sentence as a *derived* conclusion
_CONNECTIVES = (
    "therefore", "thus", "hence", "so ", "because", "since", "as a result", "driven by",
    "suggests", "indicates", "implies", "means that", "leading to", "consequently", "due to",
)
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


# --- extractors ---------------------------------------------------------------------
class StubClaimExtractor:
    """Deterministic, model-free extraction: sentence-split + connective/overlap heuristics.

    A sentence with a reasoning connective is ``derived`` (its load-bearing parents are the preceding
    anchored claims); a sentence that overlaps neither the question nor the context is an ``orphan``;
    everything else is ``anchored``. Good enough to exercise the whole pipeline offline.
    """

    async def extract(self, question: str, response: str, context: str) -> list[ExtractedClaim]:
        claims: list[ExtractedClaim] = []
        anchored_ids: list[str] = []
        for i, sent in enumerate(_split_sentences(response)):
            cid = f"c{i}"
            low = sent.lower()
            is_derived = any(k in low for k in _CONNECTIVES)
            if is_derived:
                steps = [s.strip() for s in re.split(r",|;|\band\b|\bbecause\b|\bso\b", sent) if len(s.strip()) > 8]
                parents = [ClaimParent(pid) for pid in anchored_ids[-2:]]  # lean on the last couple of facts
                claims.append(ExtractedClaim(cid, sent, "derived", parents, steps or [sent]))
            elif _overlap(sent, context) < 0.2 and _overlap(sent, question) < 0.2:
                claims.append(ExtractedClaim(cid, sent, "orphan"))
            else:
                claims.append(ExtractedClaim(cid, sent, "anchored"))
                anchored_ids.append(cid)
        return claims


_EXTRACT_SYSTEM = (
    "You decompose an ANSWER into atomic claims for a truthfulness audit. Return ONLY a JSON array; "
    "each element: {\"id\": \"c0\", \"text\": \"...\", \"kind\": \"anchored|derived|orphan\", "
    "\"parents\": [{\"id\": \"c1\", \"load_bearing\": true, \"or_group\": null}], "
    "\"reasoning_steps\": [\"...\"]}. "
    "anchored = a factual assertion meant to be grounded directly in a source. "
    "derived = a conclusion inferred from other claims (list them in parents; load_bearing=false for "
    "merely supporting, non-essential parents; give the same or_group to interchangeable alternatives). "
    "orphan = a floating aside grounded in neither a source nor other claims. "
    "Keep ids stable and referenced only after they are defined where possible."
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
            ClaimParent(str(p.get("id")), bool(p.get("load_bearing", True)), p.get("or_group"))
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


async def build_claim_nodes(
    extracted: Sequence[ExtractedClaim], *, response: str, context: str, question: str = "",
    evidence: Optional[Sequence[dict]] = None,
    grounded: Optional[Scorer] = None, attribution: Optional[Scorer] = None,
    reasoning: Optional[Callable[[Sequence[str], str], Awaitable[Optional[float]]]] = None,
) -> dict[str, ClaimNode]:
    """Bind per-claim truthfulness + reasoning scores and return the SCORED ClaimNode tree.

    ``grounded``/``attribution`` default to the deterministic overlap proxies; ``reasoning`` to the
    graded overlap. Pass NLI/judge-backed callables for the live path (e.g. wrap ``ClaudeNLIScorer``
    for grounding, and ``explainability.reasoning_fidelity`` with an NLI ``entails`` for reasoning).
    Source quality comes from the evidence support levels.
    """
    grounded = grounded or _det_grounded
    attribution = attribution or _det_grounded          # attribution ~ overlap with a cited source
    reasoning = reasoning or _det_reasoning
    evidence = evidence or []
    nodes: dict[str, ClaimNode] = {}

    for c in extracted:
        node = ClaimNode(id=c.id, text=c.text, kind=c.kind,
                         parents=[ParentLink(p.parent_id, p.load_bearing, p.or_group) for p in c.parents])
        if c.kind == "orphan":
            # STUB relevance: how much the floating fact relates to what was ASKED (not the answer
            # it came from). Deliberately thin — the real per-claim relevance judge lands later.
            node.relevance = round(_overlap(c.text, question), 4) if question else 0.3
        else:
            node.groundedness = await grounded(c.text, response, context)
            node.source_attribution = await attribution(c.text, response, context)
            node.source_quality = _quality_from_evidence(c.text, evidence)
            if c.kind == "derived":
                node.reasoning_fidelity = await reasoning(c.reasoning_steps, context)
        nodes[c.id] = node

    return score_tree(nodes)


# --- live scorer wiring (backend-agnostic: works with any anthropic-shaped async client) ------
def live_scorers(async_client: Any, model: str, *, max_concurrency: int = 2) -> dict:
    """Build NLI-backed ``grounded``/``reasoning`` callables from an async client.

    Reuses ``ClaudeNLIScorer`` (which also drives the Groq/Bedrock paths — the clients quack like
    ``anthropic.AsyncAnthropic``). Grounding is per-claim entailment against the source context;
    reasoning fidelity is the fraction of a derived claim's steps entailed by the context. Calls are
    throttled by a semaphore so free-tier rate limits (HTTP 429) aren't tripped by a burst.

    ``attribution`` is intentionally ``None`` here — a distinct "cited the right source" signal isn't
    wired yet (deferred alongside source_quality/relevance), so ``own_truthfulness`` = min(grounded,
    source_quality) rather than paying a second NLI call per claim for a placeholder.
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

    async def _skip(*_a) -> Optional[float]:      # explicit skip -> source_attribution stays unset
        return None

    return {"grounded": grounded, "attribution": _skip, "reasoning": reasoning}


def local_scorers(cfg: Any = None) -> dict:
    """Build ``grounded``/``reasoning`` from the LOCAL transformer NLI model (no API, no rate limit).

    This is the design-intended grounding path (dedicated NLI, not an LLM judge): each claim is
    entailed-checked against the source context, graded 0..1. ``attribution`` stays deferred (skip).
    Pair with :func:`prewarm_grounding` before binding for batched speed on a slow device.
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

    async def _skip(*_a) -> Optional[float]:
        return None

    return {"grounded": grounded, "attribution": _skip, "reasoning": reasoning}


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
