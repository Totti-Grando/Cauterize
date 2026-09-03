"""Evaluator-reliability meta-metric (G11).

Every Red band and every gate comes from a scorer that can itself be wrong. Against a human-validated
sample, this computes each dimension's evaluator precision / recall / FPR / FNR — where the "positive"
event is *the harness flagging a failure* (verdict 0). The dangerous error is a **false negative**:
the harness passed an answer the human failed (a false Approve). Gate scorers are therefore held to a
near-zero FNR (fail-closed); quality scorers report both directions.

The honest floor is the human sample's inter-rater agreement, recorded verbatim — nothing claims to
be more reliable than the humans it was checked against.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from ..contracts import Band, Dimension, EvaluatorReliability, RiskPolicy, ScorerReliability, Tier


@dataclass(frozen=True)
class ReliabilityItem:
    """One human-vs-harness comparison. Scores are 0 (fail/violation) or 1 (pass)."""

    dimension: Dimension
    human_score: int
    harness_score: int


def _safe_div(num: int, den: int, *, default: float) -> float:
    return num / den if den else default


def _band_from_fnr(fnr: float, *, is_gate: bool, fnr_target: float) -> Band:
    """A high FNR is the dangerous failure. Gate scorers must stay within the fail-closed target."""
    if is_gate:
        return Band.GREEN if fnr <= fnr_target else Band.RED  # gate: fail-closed, no Amber
    if fnr <= fnr_target:
        return Band.GREEN
    if fnr <= 3 * fnr_target:
        return Band.AMBER
    return Band.RED


def evaluator_reliability(
    sample: Sequence[ReliabilityItem],
    policy: RiskPolicy,
    *,
    inter_rater_agreement: Optional[float] = None,
    fnr_target_gate: float = 0.05,
) -> EvaluatorReliability:
    """Compute the evaluator's per-dimension error profile against a human-labelled sample."""
    by_dim: dict[Dimension, list[ReliabilityItem]] = {}
    for it in sample:
        by_dim.setdefault(it.dimension, []).append(it)

    scorers: list[ScorerReliability] = []
    severity = {Band.GREEN: 0, Band.AMBER: 1, Band.RED: 2}
    worst = Band.GREEN
    for dim, items in by_dim.items():
        tp = sum(1 for i in items if i.harness_score == 0 and i.human_score == 0)
        fp = sum(1 for i in items if i.harness_score == 0 and i.human_score == 1)
        fn = sum(1 for i in items if i.harness_score == 1 and i.human_score == 0)
        tn = sum(1 for i in items if i.harness_score == 1 and i.human_score == 1)
        precision = _safe_div(tp, tp + fp, default=1.0)
        recall = _safe_div(tp, tp + fn, default=1.0)
        fpr = _safe_div(fp, fp + tn, default=0.0)
        fnr = _safe_div(fn, fn + tp, default=0.0)
        is_gate = policy.tiers.get(dim) is Tier.CRITICAL
        band = _band_from_fnr(fnr, is_gate=is_gate, fnr_target=fnr_target_gate)
        dp = policy.dimensions.get(dim)
        scorers.append(ScorerReliability(
            dimension=dim, dim_id=dp.dim_id if dp else "", precision=round(precision, 4),
            recall=round(recall, 4), fpr=round(fpr, 4), fnr=round(fnr, 4), band=band,
            is_gate=is_gate, fail_closed_ok=(not is_gate) or fnr <= fnr_target_gate,
            sample_size=len(items),
        ))
        if severity[band] > severity[worst]:
            worst = band

    return EvaluatorReliability(
        scorers=scorers, inter_rater_agreement=inter_rater_agreement, band=worst,
        fnr_target_gate=fnr_target_gate,
    )
