"""Time-series, drift, trend, KRIs (G6).

Persists each metric per ``use_case × dimension`` over time (append-only JSONL, mirroring the
AuditLog pattern), and derives a trend arrow and a drift number from the series. KRIs turn a Red
band or excessive drift into an alert with an SLA and a re-evaluation trigger.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Optional

from ..contracts import Band, Dimension, DimensionAssessment, KRIAlert, MetricPoint, RiskPolicy
from ..logging_config import get_logger

log = get_logger("layer_c.monitoring")

# A dimension is "worsening" if its metric moved against it by at least this much between points.
_TREND_EPS = 0.02
# Drift beyond this (absolute change in the metric over the window) raises a KRI.
_DRIFT_LIMIT = 0.15


def _trend_from_deltas(direction: str, first: float, last: float) -> "str":
    """Return 'up' (worsening), 'down' (improving), or 'flat' for a metric move.

    For lower_is_better metrics an increase is worsening; for higher_is_better a decrease is.
    """
    delta = last - first
    if abs(delta) < _TREND_EPS:
        return "flat"
    worse = delta > 0 if direction == "lower_is_better" else delta < 0
    return "up" if worse else "down"


class MonitoringStore:
    """Append-only per-(use_case, dimension) metric history."""

    def __init__(self, path: Optional[Path] = None):
        self._path = Path(path) if path else None
        self._points: list[MetricPoint] = []
        if self._path and self._path.exists():
            for line in self._path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line:
                    try:
                        self._points.append(MetricPoint.model_validate_json(line))
                    except ValueError:
                        continue

    def series(self, use_case: str, dimension: Dimension) -> list[MetricPoint]:
        return [p for p in self._points if p.use_case == use_case and p.dimension is dimension]

    def record(self, point: MetricPoint) -> None:
        self._points.append(point)
        if self._path:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as f:
                f.write(point.model_dump_json() + "\n")

    def trend(self, use_case: str, dimension: Dimension, direction: str) -> str:
        """Trend arrow over the recorded series for a dimension (prior points only)."""
        vals = [p.value for p in self.series(use_case, dimension)]
        if len(vals) < 2:
            return "flat"
        return _trend_from_deltas(direction, vals[0], vals[-1])

    def drift(self, use_case: str, dimension: Dimension) -> Optional[float]:
        """Absolute change in the metric across the recorded window (None if <2 points)."""
        vals = [p.value for p in self.series(use_case, dimension)]
        if len(vals) < 2:
            return None
        return abs(vals[-1] - vals[0])


def evaluate_kris(
    use_case: str,
    assessments: Iterable[DimensionAssessment],
    policy: RiskPolicy,
    history: Optional[MonitoringStore] = None,
) -> list[KRIAlert]:
    """Raise a KRI for any Red band (re-evaluate; short SLA for gating dims) or excessive drift."""
    alerts: list[KRIAlert] = []
    for a in assessments:
        tier = policy.tiers.get(a.dimension)
        gating = tier is not None and tier.value == "critical"
        if a.band is Band.RED:
            alerts.append(KRIAlert(
                dimension=a.dimension, dim_id=a.dim_id, kri="band_red",
                message=f"{a.dimension.value} banded RED (risk {a.risk}).",
                reevaluate=True, sla_hours=24 if gating else 72,
            ))
        if history is not None:
            d = history.drift(use_case, a.dimension)
            if d is not None and d >= _DRIFT_LIMIT:
                alerts.append(KRIAlert(
                    dimension=a.dimension, dim_id=a.dim_id, kri="drift",
                    message=f"{a.dimension.value} drifted {d:.3f} over the window.",
                    reevaluate=True, sla_hours=48,
                ))
    if alerts:
        log.info("use_case %s raised %d KRI alert(s)", use_case, len(alerts))
    return alerts
