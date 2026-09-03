"""Layer C G1: RiskPolicy load + band validation (extends WeightConfig, never breaks it)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from aah.config import default_risk_policy, default_weight_config
from aah.contracts import Dimension, GarBands, RiskPolicy, Tier, WeightConfig


def test_default_risk_policy_validates_and_covers_every_dimension():
    policy = default_risk_policy()
    # A RiskPolicy IS a WeightConfig (superset), so it still carries the tier map + gates.
    assert isinstance(policy, WeightConfig)
    for dim in Dimension:
        assert dim in policy.tiers
        assert dim in policy.dimensions          # every dimension carries governance bands
    assert policy.policy_version == "g0"


def test_scored_dimensions_have_full_gar_bands():
    policy = default_risk_policy()
    for dim, tier in policy.tiers.items():
        dp = policy.dimensions[dim]
        if tier in (Tier.MAJOR, Tier.MINOR):
            # scored dimensions must carry a full G/A/R band (Amber present)
            assert dp.gar_bands.amber is not None
        if tier is Tier.CRITICAL:
            # zero-tolerance criticals may omit Amber
            assert dp.gar_bands.zero_tolerance


def test_policy_without_bands_is_rejected():
    # A RiskPolicy missing bands for a scored dimension is non-compliant and must not construct.
    wc = default_weight_config()
    with pytest.raises((ValidationError, ValueError)):
        RiskPolicy(
            tiers=wc.tiers,
            gate_thresholds=wc.gate_thresholds,
            dimensions={},          # <- no bands at all
        )


def test_missing_amber_on_scored_dimension_is_rejected():
    policy = default_risk_policy()
    # Drop Amber from a scored (MAJOR) dimension -> non-compliant at construction/load.
    broken = dict(policy.dimensions)
    ac = broken[Dimension.ANSWER_CORRECTNESS]
    broken[Dimension.ANSWER_CORRECTNESS] = ac.model_copy(
        update={"gar_bands": GarBands(direction="higher_is_better", green=0.9, amber=None)}
    )
    with pytest.raises((ValidationError, ValueError)):
        RiskPolicy(tiers=policy.tiers, gate_thresholds=policy.gate_thresholds, dimensions=broken)


def test_risk_policy_does_not_mutate_weight_config_defaults():
    # Building a RiskPolicy leaves the plain WeightConfig default untouched (no shared-state drift).
    assert default_weight_config().major_minor_ratio == 2.0
    assert not hasattr(default_weight_config(), "dimensions")
