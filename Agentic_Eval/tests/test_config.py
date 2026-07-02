"""WeightConfig defaults + the frozen policy table (spec §7.1)."""

from __future__ import annotations

from aah.config import default_weight_config
from aah.contracts import Dimension, Tier


def test_every_dimension_has_a_tier():
    cfg = default_weight_config()
    for dim in Dimension:
        assert dim in cfg.tiers


def test_critical_dimensions_have_gate_thresholds():
    cfg = default_weight_config()
    criticals = [d for d, t in cfg.tiers.items() if t is Tier.CRITICAL]
    assert criticals
    for d in criticals:
        assert d in cfg.gate_thresholds


def test_default_ratio_is_two():
    assert default_weight_config().major_minor_ratio == 2.0
