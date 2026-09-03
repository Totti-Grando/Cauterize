"""Metric-adapter registry (G3) — verdicts -> a canonical metric value per dimension.

Each dimension maps its binary verdicts to the metric its G/A/R bands are defined on, on the SAME
scale as those bands (a ``lower_is_better`` band expects a failure/incident *rate*; a
``higher_is_better`` band expects a pass rate). Adapters that genuinely need extra data —
paraphrase repeats for stability, cohort labels for fairness — declare it and **abstain** (return a
``None`` value) rather than assert a rate on data they don't have (the honest-floor principle that
G14 later formalises with a minimum sample size).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ..contracts import AuditRecord, Dimension, RiskPolicy, Verdict
from .omission import omission_metric

# Dimensions whose real metric needs inputs a single generic run doesn't carry.
EXTRA_DATA_NEEDS: dict[Dimension, tuple[str, ...]] = {
    Dimension.SAFETY_FAIRNESS: ("cohort_labels",),   # delta_fpr/fnr needs cohorts
    Dimension.ROBUSTNESS: ("repeats",),              # paraphrase_variance needs repeats
}


@dataclass(frozen=True)
class MetricResult:
    """One dimension's canonical metric. ``value is None`` means the adapter abstained."""

    dimension: Dimension
    metric_id: str
    value: Optional[float]
    direction: str                       # lower_is_better | higher_is_better
    abstained: bool = False
    reason: str = ""
    inputs: tuple[str, ...] = field(default_factory=tuple)
    ci_low: Optional[float] = None       # G14: confidence interval for banded rates
    ci_high: Optional[float] = None
    sample_size: Optional[int] = None


def verdicts_by_dimension(audit: AuditRecord) -> dict[Dimension, list[Verdict]]:
    """Group the run's verdicts under their rubric dimension."""
    dim_of = {q.id: q.dimension for q in audit.rubric}
    out: dict[Dimension, list[Verdict]] = {}
    for v in audit.verdicts:
        dim = dim_of.get(v.question_id)
        if dim is not None:
            out.setdefault(dim, []).append(v)
    return out


def _failure_rate(verdicts: list[Verdict]) -> float:
    return sum(1 for v in verdicts if v.score == 0) / len(verdicts)


def _pass_rate(verdicts: list[Verdict]) -> float:
    return sum(v.score for v in verdicts) / len(verdicts)


def _attack_success_rate(verdicts: list[Verdict]) -> float:
    flags = [bool(v.attack_success) for v in verdicts if v.attack_success is not None]
    return (sum(flags) / len(flags)) if flags else _failure_rate(verdicts)


def compute_metric(
    dimension: Dimension,
    verdicts: list[Verdict],
    policy: RiskPolicy,
    context: Optional[dict] = None,
) -> MetricResult:
    """Canonical metric value for one dimension from its verdicts (+ optional extra data)."""
    ctx = context or {}
    dp = policy.dimensions.get(dimension)
    metric_id = dp.metric_id if dp else ""
    direction = dp.gar_bands.direction if dp else "higher_is_better"

    def result(value, *, abstained=False, reason="", inputs=()):
        return MetricResult(dimension, metric_id, value, direction, abstained, reason, tuple(inputs))

    if not verdicts:
        return result(None, abstained=True, reason="no verdicts for dimension")

    # Adapters that need inputs a generic run lacks -> abstain rather than guess.
    for need in EXTRA_DATA_NEEDS.get(dimension, ()):  # cohort_labels / repeats
        if not ctx.get(need):
            return result(None, abstained=True, reason=f"missing required input: {need}")

    # G14: completeness -> source-recall + seeded-catch with a Wilson CI + min sample.
    if dimension is Dimension.COMPLETENESS and ctx.get("omission"):
        om = omission_metric(ctx["omission"])
        return MetricResult(dimension, metric_id, om.value, direction, om.abstained, om.reason,
                            ("omission",), om.ci_low, om.ci_high, om.sample_size)

    if dimension is Dimension.INJECTION_RESISTANCE:
        return result(_attack_success_rate(verdicts), inputs=("attack_success", "verdicts"))

    value = _failure_rate(verdicts) if direction == "lower_is_better" else _pass_rate(verdicts)
    return result(value, inputs=("verdicts",))


def compute_metrics(
    audit: AuditRecord, policy: RiskPolicy, context: Optional[dict] = None
) -> dict[Dimension, MetricResult]:
    """Canonical metric per dimension present in the run."""
    return {
        dim: compute_metric(dim, verdicts, policy, context)
        for dim, verdicts in verdicts_by_dimension(audit).items()
    }
