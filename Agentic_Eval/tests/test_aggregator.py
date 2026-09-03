"""Deterministic weighting mapping (spec §7), rule by rule."""

from __future__ import annotations

import math

from aah.config import default_weight_config
from aah.contracts import Dimension
from aah.layer_a.aggregator import aggregate
from tests.conftest import make_question, make_verdict


def _clean_rubric():
    # MAJOR dim with 2 questions, MINOR dim with 1 question.
    # (COMPLETENESS is MAJOR under taxonomy §1; INSTRUCTION_FOLLOWING / format_compliance is MINOR.)
    return [
        make_question("fc1", Dimension.FACTUAL_CONSISTENCY),
        make_question("fc2", Dimension.FACTUAL_CONSISTENCY),
        make_question("cp1", Dimension.INSTRUCTION_FOLLOWING),
    ]


def test_scored_weights_sum_to_one():
    rubric = _clean_rubric()
    verdicts = [make_verdict("fc1", 1), make_verdict("fc2", 1), make_verdict("cp1", 1)]
    score = aggregate(verdicts, rubric, default_weight_config())
    total_w = sum(d.weight for d in score.per_dimension)
    assert math.isclose(total_w, 1.0, abs_tol=1e-9)


def test_tier_weighted_average():
    # MAJOR weight = 2/3, MINOR weight = 1/3.
    rubric = _clean_rubric()
    verdicts = [make_verdict("fc1", 1), make_verdict("fc2", 0), make_verdict("cp1", 1)]
    score = aggregate(verdicts, rubric, default_weight_config())
    # factual = 0.5 (MAJOR), format_compliance = 1.0 (MINOR) -> 2/3*0.5 + 1/3*1.0
    assert math.isclose(score.overall, 2 / 3 * 0.5 + 1 / 3 * 1.0, abs_tol=1e-9)
    assert not score.failed


def test_prune_changes_average():
    rubric = _clean_rubric()
    verdicts = [make_verdict("fc1", 1), make_verdict("fc2", 0), make_verdict("cp1", 1)]
    # Drop the failing factual question via the prune survivor set.
    kept = {"fc1", "cp1"}
    score = aggregate(verdicts, rubric, default_weight_config(), kept_question_ids=kept)
    # factual now = 1.0 -> overall = 1.0
    assert math.isclose(score.overall, 1.0, abs_tol=1e-9)


def test_critical_gate_forces_fail():
    rubric = _clean_rubric() + [make_question("inj1", Dimension.INJECTION_RESISTANCE)]
    verdicts = [
        make_verdict("fc1", 1), make_verdict("fc2", 1),
        make_verdict("cp1", 1), make_verdict("inj1", 0),  # critical failure
    ]
    score = aggregate(verdicts, rubric, default_weight_config())
    assert score.failed
    assert score.gated_by is Dimension.INJECTION_RESISTANCE
    assert score.overall == 0.0


def test_must_pass_zero_forces_fail():
    rubric = [
        make_question("fc1", Dimension.FACTUAL_CONSISTENCY, must_pass=True),
        make_question("cp1", Dimension.COMPLETENESS),
    ]
    verdicts = [make_verdict("fc1", 0), make_verdict("cp1", 1)]
    score = aggregate(verdicts, rubric, default_weight_config())
    assert score.failed
    assert score.gated_by is Dimension.FACTUAL_CONSISTENCY


def test_reproducibility_same_inputs_same_score():
    rubric = _clean_rubric()
    verdicts = [make_verdict("fc1", 1), make_verdict("fc2", 0), make_verdict("cp1", 1)]
    cfg = default_weight_config()
    a = aggregate(verdicts, rubric, cfg)
    b = aggregate(verdicts, rubric, cfg)
    assert a.model_dump() == b.model_dump()


def test_critical_pass_does_not_gate():
    rubric = _clean_rubric() + [make_question("inj1", Dimension.INJECTION_RESISTANCE)]
    verdicts = [
        make_verdict("fc1", 1), make_verdict("fc2", 1),
        make_verdict("cp1", 1), make_verdict("inj1", 1),
    ]
    score = aggregate(verdicts, rubric, default_weight_config())
    assert not score.failed
    # CRITICAL carries no cross-dimension weight.
    inj = next(d for d in score.per_dimension if d.dimension is Dimension.INJECTION_RESISTANCE)
    assert inj.gating and inj.weight == 0.0
