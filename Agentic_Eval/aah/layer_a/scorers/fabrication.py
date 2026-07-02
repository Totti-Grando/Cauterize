"""Deterministic source-fabrication gate (F3, spec §6 CRITICAL gate ``source_fabrication``).

The strongest gate must run on the hardest scorer, not the softest. Source-fabrication is a
CRITICAL gating dimension, but by default NLI/source_fetch checks route to the LLM judge — so a
fabricated URL only fails if the judge happens to notice. This scorer makes fabrication an
EXACT deterministic check: every source the response cites (URL or quoted span) must be present
in the provided source material; if any is absent, the gate fails with the offending span in
evidence. Zero LLM calls, fully reproducible.
"""

from __future__ import annotations

import re

from ...contracts import BinaryQuestion, Verdict

_URL_RE = re.compile(r"https?://[^\s)\]<>\"']+", re.IGNORECASE)
# Quoted spans the response presents as verbatim source material (curly or straight quotes).
_QUOTE_RE = re.compile(r"[\"“’‘”']([^\"“’‘”']{12,})[\"“’‘”']")


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip().lower()


def _domain(url: str) -> str:
    m = re.match(r"https?://([^/\s]+)", url, re.IGNORECASE)
    return m.group(1).lower() if m else url.lower()


def extract_citations(response: str) -> tuple[list[str], list[str]]:
    """Return (urls, quotes) the response presents as sourced material."""
    urls = [u.rstrip(".,);]") for u in _URL_RE.findall(response or "")]
    quotes = [q.strip() for q in _QUOTE_RE.findall(response or "")]
    return urls, quotes


def unsupported_citations(response: str, context: str) -> list[str]:
    """Cited URLs/quotes that do NOT appear in the provided source material (fabricated)."""
    ctx = context or ""
    ctx_norm = _norm(ctx)
    urls, quotes = extract_citations(response)
    missing: list[str] = []
    for u in urls:
        if u.lower() not in ctx.lower() and _domain(u) not in ctx.lower():
            missing.append(u)
    for q in quotes:
        if _norm(q) not in ctx_norm:
            missing.append(f'"{q}"')
    return missing


class FabricationScorer:
    """Deterministic fabrication gate: cited sources must be a subset of the provided context."""

    async def score(self, question: BinaryQuestion, response: str, context: str) -> Verdict:
        missing = unsupported_citations(response, context)
        if not missing:
            urls, quotes = extract_citations(response)
            n = len(urls) + len(quotes)
            return Verdict(
                question_id=question.id,
                score=1,
                explanation=(f"all {n} cited source(s) present in the provided context"
                             if n else "no external citations to verify"),
                evidence="source_check: grounded",
            )
        offending = "; ".join(missing[:3])
        return Verdict(
            question_id=question.id,
            score=0,
            explanation=f"fabricated source(s) not present in the provided context: {offending}",
            evidence=offending,
        )
