"""WeightConfig loader (spec §7). Builds the frozen, versioned config used by the aggregator.

A WeightConfig is a pure value: the aggregator is a reproducible function of
(verdicts, WeightConfig), and the full config is written into every AuditRecord (§7.6).
The loader either builds the default from the policy table or reads a YAML override.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from ..contracts import Dimension, PruneThresholds, Tier, WeightConfig
from .policy import DEFAULT_GATE_THRESHOLDS, POLICY_TABLE


def default_weight_config(version: str = "v0") -> WeightConfig:
    """The frozen default: policy tiers + gate every CRITICAL dimension at 1.0."""

    return WeightConfig(
        tiers=dict(POLICY_TABLE),
        major_minor_ratio=2.0,
        prune_thresholds=PruneThresholds(),
        gate_thresholds=dict(DEFAULT_GATE_THRESHOLDS),
        version=version,
    )


def load_weight_config(path: str | Path) -> WeightConfig:
    """Load a WeightConfig from YAML, filling unspecified fields from the default.

    Recognised keys: ``major_minor_ratio``, ``version``, ``prune_thresholds``
    (``phi``, ``yes_rate_band``), ``gate_thresholds`` (dimension-name -> float),
    and ``tiers`` (dimension-name -> tier-name) to override the policy table.
    """

    data: dict[str, Any] = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    base = default_weight_config()

    tiers = dict(base.tiers)
    for name, tier_name in (data.get("tiers") or {}).items():
        tiers[Dimension(name)] = Tier(tier_name)

    gate_thresholds = dict(base.gate_thresholds)
    for name, thr in (data.get("gate_thresholds") or {}).items():
        gate_thresholds[Dimension(name)] = float(thr)

    pt = data.get("prune_thresholds") or {}
    prune = PruneThresholds(
        phi=float(pt.get("phi", base.prune_thresholds.phi)),
        yes_rate_band=tuple(pt.get("yes_rate_band", base.prune_thresholds.yes_rate_band)),  # type: ignore[arg-type]
    )

    return WeightConfig(
        tiers=tiers,
        major_minor_ratio=float(data.get("major_minor_ratio", base.major_minor_ratio)),
        prune_thresholds=prune,
        gate_thresholds=gate_thresholds,
        gating_min_runs=int(data.get("gating_min_runs", base.gating_min_runs)),
        version=str(data.get("version", base.version)),
    )
