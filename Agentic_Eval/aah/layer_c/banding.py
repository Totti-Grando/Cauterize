"""Banding + Likelihood×Impact (G4).

``band = f(metric_value, GarBands)`` on the "no Yellow" G/A/R scale; Likelihood from band
(Green→1, Amber→3, Red→5, representative points within the doc's G:1–2 / A:3 / R:4–5 ranges); Impact
from the policy; ``risk = L×I`` (1–25). Aggregate per use case = **max** (governing) + **mean**
(portfolio), so a single critical risk can never be averaged away.
"""

from __future__ import annotations

from typing import Optional

from ..contracts import AggregateRisk, Band, GarBands

# Representative Likelihood per band (within the doc ranges G:1–2 / A:3 / R:4–5).
_LIKELIHOOD: dict[Band, int] = {Band.GREEN: 1, Band.AMBER: 3, Band.RED: 5}

# Severity order for "worst band" comparisons.
_SEVERITY: dict[Band, int] = {Band.GREEN: 0, Band.AMBER: 1, Band.RED: 2}


def band_for(value: float, bands: GarBands) -> Band:
    """Map a metric value to a G/A/R band. Zero-tolerance metrics (Amber omitted) are Green only at
    the green boundary (0) and Red for anything worse."""
    if bands.direction == "lower_is_better":
        if value <= bands.green:
            return Band.GREEN
        if bands.amber is not None and value <= bands.amber:
            return Band.AMBER
        return Band.RED
    # higher_is_better
    if value >= bands.green:
        return Band.GREEN
    if bands.amber is not None and value >= bands.amber:
        return Band.AMBER
    return Band.RED


def likelihood_for(band: Band) -> int:
    return _LIKELIHOOD[band]


def risk_of(band: Band, impact: int) -> int:
    """Likelihood×Impact for one dimension (1–25)."""
    return _LIKELIHOOD[band] * impact


def worst_band(bands: list[Band]) -> Optional[Band]:
    """The most severe band in a list (None if empty)."""
    return max(bands, key=lambda b: _SEVERITY[b]) if bands else None


def aggregate_risk(risks: list[int]) -> AggregateRisk:
    """Governing (max) + portfolio (mean) over the per-dimension risks."""
    if not risks:
        return AggregateRisk(max=None, mean=None)
    return AggregateRisk(max=max(risks), mean=round(sum(risks) / len(risks), 3))
