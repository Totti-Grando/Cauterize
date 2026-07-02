"""Deterministic weighting mapping (spec v3 §7). [single-owner, high risk]

A score must be a reproducible function of ``(verdicts, WeightConfig)``. This module
implements §7 rules 1-6 exactly:

1. Tier each dimension: CRITICAL -> gating; MAJOR -> tierweight = major_minor_ratio;
   MINOR -> tierweight = 1.
2. No per-question weights. Within a dimension, prune redundant questions (done upstream
   in ``guards`` using phi / yes-rate), then *uniformly average* the survivors.
3. Cross-dimension weights from tiers: w_d = tierweight(d) / sum_scored tierweight. The
   scored set is MAJOR + MINOR (CRITICAL dimensions gate, they do not enter the average).
4. Gating dominates: overall = FAIL if any CRITICAL dim score < gate_thresholds[d], or any
   must-pass question == 0; else sum_scored w_d * S_d. Gates are never averaged.
5. Calibration tidies only major_minor_ratio (see ``calibration`` later); never creates a gate.
6. Reproducibility: the full WeightConfig travels in every AuditRecord.

Pruning (§7.2) is applied *before* this function via ``kept_question_ids`` so the aggregator
itself stays a pure, side-effect-free mapping. With no prune set, all questions survive.
"""

from __future__ import annotations

from typing import Iterable, Optional

from ..contracts import (
    BinaryQuestion,
    Dimension,
    DimensionScore,
    RunScore,
    Tier,
    Verdict,
    WeightConfig,
)


def tierweight(tier: Tier, major_minor_ratio: float) -> float:
    """MAJOR = ratio, MINOR = 1, CRITICAL = 0 (gating, not in the weighted sum)."""

    if tier is Tier.MAJOR:
        return major_minor_ratio
    if tier is Tier.MINOR:
        return 1.0
    return 0.0  # CRITICAL gates; it carries no cross-dimension weight


def _dimension_mean(scores: Iterable[int]) -> float:
    vals = list(scores)
    if not vals:
        raise ValueError("cannot average an empty dimension")
    return sum(vals) / len(vals)


def aggregate(
    verdicts: list[Verdict],
    rubric: list[BinaryQuestion],
    config: WeightConfig,
    kept_question_ids: Optional[set[str]] = None,
) -> RunScore:
    """Apply the §7 mapping. Pure: same args => same RunScore.

    ``kept_question_ids`` is the survivor set from the §7.2 prune step (computed in
    ``guards``). ``None`` keeps every question.
    """

    q_by_id: dict[str, BinaryQuestion] = {q.id: q for q in rubric}
    if kept_question_ids is None:
        kept_question_ids = set(q_by_id)

    # Group surviving verdicts by dimension; track must-pass failures for gating.
    by_dim: dict[Dimension, list[int]] = {}
    must_pass_fail_dims: set[Dimension] = set()
    for v in verdicts:
        if v.question_id not in kept_question_ids:
            continue
        q = q_by_id.get(v.question_id)
        if q is None:
            raise ValueError(f"verdict references unknown question {v.question_id!r}")
        by_dim.setdefault(q.dimension, []).append(v.score)
        if q.must_pass and v.score == 0:
            must_pass_fail_dims.add(q.dimension)  # canonicalized below (order-independent)

    # Rule 1-2: per-dimension uniform average of survivors.
    dim_scores: dict[Dimension, float] = {
        dim: _dimension_mean(scores) for dim, scores in by_dim.items()
    }

    # Stable, deterministic iteration order over the Dimension enum.
    ordered_dims = [d for d in Dimension if d in dim_scores]

    # Rule 3: cross-dimension weights over the *scored* (MAJOR+MINOR) set only.
    scored = [d for d in ordered_dims if config.tiers[d] in (Tier.MAJOR, Tier.MINOR)]
    total_tw = sum(tierweight(config.tiers[d], config.major_minor_ratio) for d in scored)

    per_dimension: list[DimensionScore] = []
    weights: dict[Dimension, float] = {}
    for d in ordered_dims:
        tier = config.tiers[d]
        gating = tier is Tier.CRITICAL
        w = 0.0
        if not gating and total_tw > 0:
            w = tierweight(tier, config.major_minor_ratio) / total_tw
        weights[d] = w
        per_dimension.append(
            DimensionScore(
                dimension=d, tier=tier, gating=gating, score=dim_scores[d], weight=w
            )
        )

    # Rule 4: gating dominates. Check CRITICAL thresholds + must-pass failures.
    gated_by: Optional[Dimension] = None
    for d in ordered_dims:
        if config.tiers[d] is Tier.CRITICAL:
            threshold = config.gate_thresholds.get(d, 1.0)
            if dim_scores[d] < threshold:
                gated_by = d
                break
    if gated_by is None and must_pass_fail_dims:
        # Attribute by canonical Dimension order, not verdict-list order (reproducible gated_by).
        gated_by = next((d for d in Dimension if d in must_pass_fail_dims), None)

    if gated_by is not None:
        overall, failed = 0.0, True
    else:
        if scored:
            overall = sum(weights[d] * dim_scores[d] for d in scored)
        else:
            # Gate-only rubric (all CRITICAL dims): no MAJOR/MINOR quality signal to average.
            # Nothing failed, so report a pass (1.0) rather than 0.0, which reads as worst-possible.
            overall = 1.0
        overall = min(1.0, max(0.0, overall))  # clamp float drift / calibrated ratios into [0,1]
        failed = False

    return RunScore(
        per_question=list(verdicts),
        per_dimension=per_dimension,
        overall=overall,
        failed=failed,
        gated_by=gated_by,
        weight_config_version=config.version,
    )
