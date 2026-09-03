"""Explainability metric (G12) — reasoning-fidelity, kept distinct from traceability/transparency.

Decompose an answer's stated rationale into atomic steps; each step must be **entailed by the cited
evidence**. The score is the fraction of steps that are entailed. An optional sampled human
usefulness rating (1–10) is folded in as a secondary signal. The default entailment check reuses the
label-free content-overlap heuristic from ``guards.asserts_claim``; pass a real ``nli`` entailment
callable for the live path.
"""

from __future__ import annotations

from typing import Callable, Optional, Sequence

from ..determinism_guards import asserts_claim

Entails = Callable[[str, str], bool]


def _default_entails(step: str, evidence_text: str) -> bool:
    # A step is "entailed" if the evidence actually makes that claim (content-word overlap).
    return asserts_claim(step, evidence_text)


def reasoning_fidelity(
    steps: Sequence[str], evidence: Sequence[str], entails: Optional[Entails] = None
) -> Optional[float]:
    """Fraction of rationale steps entailed by the cited evidence (None if there is no rationale)."""
    steps = [s for s in steps if s.strip()]
    if not steps:
        return None  # no stated rationale -> abstain rather than score
    entails = entails or _default_entails
    evidence_text = "\n".join(evidence)
    entailed = sum(1 for s in steps if entails(s, evidence_text))
    return entailed / len(steps)


def explainability_score(
    steps: Sequence[str],
    evidence: Sequence[str],
    *,
    usefulness: Optional[float] = None,     # sampled human rating, 1–10
    entails: Optional[Entails] = None,
) -> Optional[float]:
    """Combine reasoning-fidelity with an optional human usefulness rating into one 0–1 score."""
    fidelity = reasoning_fidelity(steps, evidence, entails)
    if fidelity is None:
        return None
    if usefulness is None:
        return fidelity
    return round((fidelity + max(0.0, min(1.0, usefulness / 10.0))) / 2.0, 4)
