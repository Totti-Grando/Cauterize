"""R5: focus profile + effective weight. Focus boosts scored weight and shifts overall; it never
changes tiers or disables a gate."""

from __future__ import annotations

import math

from aah.config import default_weight_config
from aah.config.taxonomy import resolve_focus
from aah.contracts import Category, Dimension
from aah.layer_a.aggregator import aggregate, effective_weight
from tests.conftest import make_question, make_verdict


def test_resolve_focus_by_category_and_dimension():
    robustness = resolve_focus(["robustness"])
    assert Dimension.INJECTION_RESISTANCE in robustness  # prompt_injection_resistance
    assert Dimension.ROBUSTNESS in robustness            # paraphrase_stability
    # by taxonomy name and by frozen value both resolve to the same dim
    assert resolve_focus(["prompt_injection_resistance"]) == frozenset({Dimension.INJECTION_RESISTANCE})
    assert resolve_focus(["injection_resistance"]) == frozenset({Dimension.INJECTION_RESISTANCE})


def test_no_focus_uses_base_tier_weights():
    cfg = default_weight_config()  # no focus
    # a MAJOR dim's effective weight equals its tier weight (boost 1.0)
    assert effective_weight(Dimension.RELEVANCE, cfg) == 2.0
    assert effective_weight(Dimension.CLARITY, cfg) == 1.0  # MINOR


def test_focus_raises_effective_weight_and_shifts_overall():
    # Two MAJOR dims, one scores 1.0, the other 0.0. No focus -> overall 0.5.
    rubric = [make_question("r1", Dimension.RELEVANCE), make_question("g1", Dimension.FACTUAL_CONSISTENCY)]
    verdicts = [make_verdict("r1", 1), make_verdict("g1", 0)]
    base = aggregate(verdicts, rubric, default_weight_config())
    assert math.isclose(base.overall, 0.5, abs_tol=1e-9)

    # Focus on relevance (the 1.0 dim) with boost 2.0 -> its weight is 2/3, overall shifts up.
    focused_cfg = default_weight_config(focus=["relevance"], focus_boost=2.0)
    focused = aggregate(verdicts, rubric, focused_cfg)
    assert math.isclose(focused.overall, (2 / 3) * 1.0 + (1 / 3) * 0.0, abs_tol=1e-9)
    assert focused.overall > base.overall


def test_focus_cannot_disable_a_gate():
    # Focus entirely on Communication (all MINOR); a Privacy/Security CRITICAL still gates.
    cfg = default_weight_config(focus=["communication"])
    rubric = [
        make_question("c1", Dimension.CLARITY),
        make_question("leak1", Dimension.PII_LEAKAGE),
    ]
    verdicts = [make_verdict("c1", 1), make_verdict("leak1", 0)]  # PII leak
    score = aggregate(verdicts, rubric, cfg)
    assert score.failed and score.gated_by is Dimension.PII_LEAKAGE
    # CRITICAL still carries no weight even under focus
    assert effective_weight(Dimension.PII_LEAKAGE, cfg) == 0.0


def test_focus_does_not_change_tiers():
    plain = default_weight_config()
    focused = default_weight_config(focus=["communication"])
    assert plain.tiers == focused.tiers  # tier mechanism untouched by focus
