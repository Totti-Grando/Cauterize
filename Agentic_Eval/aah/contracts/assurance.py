"""Layer C governance contracts (Stage 1, items G1–G2).

These EXTEND the frozen §4 contracts; they never modify them. ``RiskPolicy`` is a superset of
``WeightConfig`` (adds per-dimension governance metadata + bands); ``AssuranceRecord`` is a superset
of ``AuditRecord`` (adds the risk assessment, disposition, evidence, reviewers, and retention). A
legacy run with no governance config still produces a valid v1 ``AuditRecord``; a governed run
produces a v2 ``AssuranceRecord`` that also validates as an ``AuditRecord``.

The gate property is preserved everywhere downstream: a critical Red or a must-pass failure can
never aggregate into an APPROVE (governance §5/§9).
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import Field, model_validator

from .enums import Band, Dimension, Disposition, LineOfDefence, Tier, Trend
from .models import AuditRecord, WeightConfig, _Frozen


# --- G1: RiskPolicy (extends WeightConfig) -----------------------------------------
class GarBands(_Frozen):
    """Green/Amber/Red boundaries for one metric.

    ``direction`` says which way is good. Boundaries are inclusive on the Green side:
      * lower_is_better:  value <= green -> GREEN; value <= amber -> AMBER; else RED.
      * higher_is_better: value >= green -> GREEN; value >= amber -> AMBER; else RED.
    ``zero_tolerance`` critical metrics omit Amber: value <= green (i.e. 0) -> GREEN, else RED.
    """

    direction: Literal["lower_is_better", "higher_is_better"]
    green: float
    amber: Optional[float] = None
    zero_tolerance: bool = False


class DimensionPolicy(_Frozen):
    """The governance metadata one dimension carries into every record (G1)."""

    dim_id: str                                   # DIM-##
    metric_id: str                                # M-##
    gar_bands: GarBands
    impact: int = Field(ge=1, le=5)               # I in L×I
    atlas_stripe: str = ""
    control_objective: str = ""
    anchors: list[str] = Field(default_factory=list)  # regulatory frameworks (G8)


class RiskPolicy(WeightConfig):
    """WeightConfig + per-dimension governance bands and metadata.

    Load-time validation (G1): every dimension in the tier map must carry a ``DimensionPolicy``;
    every SCORED (MAJOR/MINOR) dimension must carry a full G/A/R band (Amber present). Zero-tolerance
    critical dimensions may omit Amber. A policy missing bands is non-compliant and is rejected here.
    """

    dimensions: dict[Dimension, DimensionPolicy] = Field(default_factory=dict)
    policy_version: str = "g0"

    @model_validator(mode="after")
    def _require_bands(self) -> "RiskPolicy":
        for dim, tier in self.tiers.items():
            dp = self.dimensions.get(dim)
            if dp is None:
                raise ValueError(
                    f"RiskPolicy non-compliant: dimension {dim.value!r} has no G/A/R bands"
                )
            scored = tier in (Tier.MAJOR, Tier.MINOR)
            if scored and not dp.gar_bands.zero_tolerance and dp.gar_bands.amber is None:
                raise ValueError(
                    f"RiskPolicy non-compliant: scored dimension {dim.value!r} is missing its Amber band"
                )
        return self


# --- G2: AssuranceRecord (extends AuditRecord) -------------------------------------
class DimensionAssessment(_Frozen):
    """One dimension's governed result. metric/band/likelihood/risk are Optional so a dimension
    can abstain (e.g. below the minimum sample size, G14) rather than assert a rate on noise."""

    dimension: Dimension
    dim_id: str
    metric_id: str
    metric_value: Optional[float] = None
    band: Optional[Band] = None
    likelihood: Optional[int] = None
    impact: int = Field(ge=1, le=5)
    risk: Optional[int] = None           # L×I (1–25) when banded
    trend: Trend = Trend.FLAT
    anchors: list[str] = Field(default_factory=list)  # regulatory frameworks in the record (G8)
    # G14: a banded rate carries a confidence interval + sample size; below the minimum it abstains.
    ci_low: Optional[float] = None
    ci_high: Optional[float] = None
    sample_size: Optional[int] = None


class AggregateRisk(_Frozen):
    """Per use case: max (governing) and mean (portfolio) over the dimension risks."""

    max: Optional[int] = None
    mean: Optional[float] = None


class EvidenceLink(_Frozen):
    url: str
    type: str = ""            # dashboard | log | test-result | human-review
    description: str = ""


class Reviewer(_Frozen):
    id: str
    lod: LineOfDefence
    timestamp: str            # ISO-8601


class Override(_Frozen):
    """A contested / overridden disposition (G15). Append-only: the original is never erased."""

    original_disposition: Disposition
    new_disposition: Disposition
    rationale: str
    reviewer_id: str
    timestamp: str
    lod: LineOfDefence


class CoverageScope(_Frozen):
    """What metric families this record covers, and what it explicitly does NOT (G16)."""

    in_scope: list[str] = Field(default_factory=list)
    out_of_scope: list[str] = Field(default_factory=list)
    rationale: str = ""


class MetricPoint(_Frozen):
    """One point in a metric's time-series, keyed by use_case × dimension (G6 monitoring)."""

    use_case: str
    dimension: Dimension
    metric_id: str
    value: float
    band: Optional[Band] = None
    produced_at: str = ""     # ISO-8601


class KRIAlert(_Frozen):
    """A Key Risk Indicator breach raised for a dimension (G6)."""

    dimension: Dimension
    dim_id: str
    kri: str                  # e.g. "band_red", "drift"
    message: str
    reevaluate: bool = False  # does the breach trigger a re-evaluation?
    sla_hours: int = 72       # alert-latency SLA


class ScorerReliability(_Frozen):
    """The evaluator's own error profile for one dimension vs a human sample (G11)."""

    dimension: Dimension
    dim_id: str
    precision: float
    recall: float
    fpr: float                # false-positive rate (spurious Remediate)
    fnr: float                # false-negative rate (the dangerous direction — missed problem)
    band: Band
    is_gate: bool
    fail_closed_ok: bool      # gate scorers must keep FNR within target (fail-closed)
    sample_size: int = 0


class EvaluatorReliability(_Frozen):
    """The harness's meta-metric: it measures itself against the human-validated sample (G11).

    The honest floor is the human sample's inter-rater agreement — nothing claims to be more
    reliable than the humans it was checked against.
    """

    scorers: list[ScorerReliability] = Field(default_factory=list)
    inter_rater_agreement: Optional[float] = None
    band: Band = Band.GREEN
    fnr_target_gate: float = 0.05


class AssuranceRecord(AuditRecord):
    """The governed record: an AuditRecord plus the risk assessment, disposition, evidence pack,
    3LoD reviewers, and retention. schema_version bumps to ``v2``."""

    use_case: str = ""
    atlas_stripe: str = ""
    control_objective: str = ""
    dimensions: list[DimensionAssessment] = Field(default_factory=list)
    aggregate_risk: AggregateRisk = Field(default_factory=AggregateRisk)
    disposition: Optional[Disposition] = None
    evidence_links: list[EvidenceLink] = Field(default_factory=list)
    reviewers: list[Reviewer] = Field(default_factory=list)
    attestation: str = ""
    overrides: list[Override] = Field(default_factory=list)
    coverage_scope: CoverageScope = Field(default_factory=CoverageScope)
    kri_alerts: list[KRIAlert] = Field(default_factory=list)
    evaluator_reliability: Optional[EvaluatorReliability] = None  # G11 meta-metric snapshot
    record_id: str = ""               # stable id for the immutable evidence store (G10)
    produced_at: str = ""             # ISO-8601
    retention_until: str = ""         # ISO-8601 date, ≥7 years from produced_at
    risk_policy_version: str = ""
    schema_version: str = "v2"
