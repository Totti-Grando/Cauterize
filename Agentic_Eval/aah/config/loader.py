"""WeightConfig loader (spec §7). Builds the frozen, versioned config used by the aggregator.

A WeightConfig is a pure value: the aggregator is a reproducible function of
(verdicts, WeightConfig), and the full config is written into every AuditRecord (§7.6).
The loader either builds the default from the policy table or reads a YAML override.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from typing import Iterable, Optional

from ..contracts import Dimension, DimensionPolicy, PruneThresholds, RiskPolicy, Tier, WeightConfig
from . import governance_policy as gov
from .policy import DEFAULT_GATE_THRESHOLDS, POLICY_TABLE
from .taxonomy import DIMENSION_META, resolve_focus


def _default_gating_subtypes() -> dict[Dimension, frozenset]:
    """Per-dimension gating subtypes from the taxonomy registry (only dims that have any)."""
    return {d: m.gating_subtypes for d, m in DIMENSION_META.items() if m.gating_subtypes}


def default_weight_config(
    version: str = "v1",
    focus: Optional[Iterable[str]] = None,
    focus_boost: float = 2.0,
) -> WeightConfig:
    """The frozen default: policy tiers + gate every CRITICAL dimension at 1.0.

    ``focus`` (categories or sub-dimensions) selects the focus profile (§2); it boosts the scored
    weight of those dims by ``focus_boost`` and can never disable a dimension or a gate.
    """

    return WeightConfig(
        tiers=dict(POLICY_TABLE),
        major_minor_ratio=2.0,
        prune_thresholds=PruneThresholds(),
        gate_thresholds=dict(DEFAULT_GATE_THRESHOLDS),
        gating_subtypes=_default_gating_subtypes(),
        focus_dimensions=resolve_focus(focus),
        focus_boost=focus_boost,
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
        gating_subtypes=dict(base.gating_subtypes),
        focus_dimensions=resolve_focus(data.get("focus")),
        focus_boost=float(data.get("focus_boost", base.focus_boost)),
        gating_min_runs=int(data.get("gating_min_runs", base.gating_min_runs)),
        version=str(data.get("version", base.version)),
    )


# --- Layer C: RiskPolicy (WeightConfig + governance bands & metadata, G1) -----------
def _default_dimension_policies() -> dict[Dimension, DimensionPolicy]:
    """Assemble a DimensionPolicy for every dimension from the governance_policy tables."""
    return {
        dim: DimensionPolicy(
            dim_id=gov.DIM_IDS[dim],
            metric_id=gov.METRIC_IDS[dim],
            gar_bands=gov.DEFAULT_GAR_BANDS[dim],
            impact=gov.IMPACT_BY_DIMENSION[dim],
            atlas_stripe=gov.ATLAS_STRIPE.get(dim, ""),
            control_objective=gov.CONTROL_OBJECTIVE.get(dim, ""),
            anchors=gov.anchors_for(dim),
        )
        for dim in POLICY_TABLE
    }


def default_risk_policy(version: str = "g0") -> RiskPolicy:
    """The frozen default RiskPolicy: the default WeightConfig plus the governance bands/metadata.

    Runs the G1 band validation on construction — every scored dimension must carry full G/A/R
    bands (zero-tolerance criticals may omit Amber), else construction raises.
    """
    wc = default_weight_config()
    return RiskPolicy(
        tiers=wc.tiers,
        major_minor_ratio=wc.major_minor_ratio,
        prune_thresholds=wc.prune_thresholds,
        gate_thresholds=wc.gate_thresholds,
        gating_subtypes=wc.gating_subtypes,
        focus_dimensions=wc.focus_dimensions,
        focus_boost=wc.focus_boost,
        gating_min_runs=wc.gating_min_runs,
        version=wc.version,
        dimensions=_default_dimension_policies(),
        policy_version=version,
    )


def load_risk_policy(path: str | Path) -> RiskPolicy:
    """Load a RiskPolicy from YAML, filling unspecified fields from the default.

    Recognises everything ``load_weight_config`` does, plus ``policy_version`` and a ``dimensions``
    map of ``dimension-name -> {dim_id, metric_id, impact, atlas_stripe, control_objective,
    anchors[], gar_bands: {direction, green, amber, zero_tolerance}}`` to override bands/metadata.
    The same G1 band validation runs on the result.
    """
    data: dict[str, Any] = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    wc = load_weight_config(path)  # reuse the WeightConfig half (tiers/thresholds/ratio/version)

    dims = _default_dimension_policies()
    for name, patch in (data.get("dimensions") or {}).items():
        dim = Dimension(name)
        base_dp = dims[dim]
        gb = patch.get("gar_bands") or {}
        bands = base_dp.gar_bands.model_copy(update={
            k: gb[k] for k in ("direction", "green", "amber", "zero_tolerance") if k in gb
        })
        dims[dim] = base_dp.model_copy(update={
            **{k: patch[k] for k in ("dim_id", "metric_id", "impact", "atlas_stripe",
                                     "control_objective", "anchors") if k in patch},
            "gar_bands": bands,
        })

    return RiskPolicy(
        tiers=wc.tiers,
        major_minor_ratio=wc.major_minor_ratio,
        prune_thresholds=wc.prune_thresholds,
        gate_thresholds=wc.gate_thresholds,
        gating_subtypes=wc.gating_subtypes,
        focus_dimensions=wc.focus_dimensions,
        focus_boost=wc.focus_boost,
        gating_min_runs=wc.gating_min_runs,
        version=wc.version,
        dimensions=dims,
        policy_version=str(data.get("policy_version", "g0")),
    )
