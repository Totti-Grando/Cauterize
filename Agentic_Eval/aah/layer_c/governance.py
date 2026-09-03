"""Layer C — governance: AuditRecord -> AssuranceRecord (Stage 1, Phases 1–3).

Turns an evaluator ``AuditRecord`` into a governed ``AssuranceRecord``: computes each dimension's
canonical metric (G3), bands it and scores Likelihood×Impact (G4), aggregates the risk, stamps the
regulatory anchors (G8) and trend from the metric history (G6), raises KRIs (G6), records the
automated cross-family 2LoD challenge (G7), and decides the disposition (G5) — all while preserving
the gate (a critical Red or must-pass failure can never present as APPROVE). Stamps coverage (G16),
retention, a stable record id (G10), and the risk-policy metadata.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Iterable, Optional

from ..contracts import (
    AssuranceRecord,
    AuditRecord,
    Band,
    CoverageScope,
    Dimension,
    DimensionAssessment,
    EvidenceLink,
    LineOfDefence,
    MetricPoint,
    Reviewer,
    RiskPolicy,
    Trend,
)
from .anchors import anchors_for
from .banding import aggregate_risk, band_for, likelihood_for, risk_of, worst_band
from .disposition import DispositionInputs, decide
from .metrics import compute_metrics
from .monitoring import MonitoringStore, evaluate_kris
from .three_lod import automated_2lod_cleared, cross_family_challenge_reviewer

# G16: the metric families this harness covers, and the one it explicitly does NOT.
_IN_SCOPE = ["model_answer", "data_privacy", "ethics_social", "compliance_governance"]
_OUT_OF_SCOPE = ["operational_resilience"]
_SCOPE_RATIONALE = (
    "Operational resilience (availability, BC/DR, third-party SLA uptime, infrastructure attacks) "
    "is not an answer-quality concern and belongs to operational-resilience testing (OSFI E-21 / "
    "B-10 operational). This record makes no resilience coverage claim."
)

_RETENTION_YEARS = 7


def default_coverage_scope() -> CoverageScope:
    """The fixed coverage statement (G16) — resilience explicitly out of scope."""
    return CoverageScope(in_scope=list(_IN_SCOPE), out_of_scope=list(_OUT_OF_SCOPE),
                         rationale=_SCOPE_RATIONALE)


def _dim_order(dim: Dimension) -> int:
    return list(Dimension).index(dim)


def to_assurance_record(
    audit: AuditRecord,
    policy: RiskPolicy,
    *,
    use_case: str = "",
    atlas_stripe: Optional[str] = None,
    control_objective: Optional[str] = None,
    reviewers: Iterable[Reviewer] = (),
    evidence_links: Iterable[EvidenceLink] = (),
    attestation: str = "",
    context: Optional[dict] = None,
    evidence_complete: Optional[bool] = None,
    sign_off_2lod: Optional[bool] = None,
    history: Optional[MonitoringStore] = None,
    reliability: Optional["EvaluatorReliability"] = None,
    produced_at: Optional[datetime] = None,
) -> AssuranceRecord:
    """Wrap an ``AuditRecord`` as a governed ``AssuranceRecord`` under ``policy``.

    ``history`` (a ``MonitoringStore``) enables per-dimension trend + drift KRIs and is appended with
    this run's points. ``evidence_complete`` / ``sign_off_2lod`` default from the passed evidence /
    2LoD reviewers (2LoD also auto-clears when a cross-family reference judged the run). ``context``
    supplies extra data (cohort labels, repeats) for adapters that need it.
    """
    reviewers = list(reviewers)
    evidence_links = list(evidence_links)
    now = produced_at or datetime.now()
    stamp = now.isoformat(timespec="seconds")
    retention = now + timedelta(days=_RETENTION_YEARS * 365 + 2)

    # Auto-attach the cross-family 2LoD challenge reviewer, if one was performed.
    challenge = cross_family_challenge_reviewer(audit, stamp)
    if challenge is not None and not any(r.lod is LineOfDefence.SECOND for r in reviewers):
        reviewers.append(challenge)

    if evidence_complete is None:
        evidence_complete = bool(evidence_links)
    if sign_off_2lod is None:
        sign_off_2lod = any(r.lod is LineOfDefence.SECOND for r in reviewers) or automated_2lod_cleared(audit)

    # --- G3/G4/G6/G8: metric -> band -> L×I, trend, anchors -----------------------------
    metrics = compute_metrics(audit, policy, context)
    assessments: list[DimensionAssessment] = []
    risks: list[int] = []
    banded: list[Band] = []
    for dim in sorted(metrics, key=_dim_order):
        mr = metrics[dim]
        dp = policy.dimensions.get(dim)
        impact = dp.impact if dp else 3
        band = likelihood = risk = None
        trend = Trend.FLAT
        if mr.value is not None and dp is not None:
            band = band_for(mr.value, dp.gar_bands)
            likelihood = likelihood_for(band)
            risk = risk_of(band, impact)
            risks.append(risk)
            banded.append(band)
            if history is not None:
                # Record this run's point, then read the trend over the full series (oldest->now).
                history.record(MetricPoint(use_case=use_case, dimension=dim, metric_id=mr.metric_id,
                                           value=mr.value, band=band, produced_at=stamp))
                trend = Trend(history.trend(use_case, dim, dp.gar_bands.direction))
        assessments.append(DimensionAssessment(
            dimension=dim, dim_id=dp.dim_id if dp else "", metric_id=mr.metric_id,
            metric_value=mr.value, band=band, likelihood=likelihood, impact=impact, risk=risk,
            trend=trend, anchors=anchors_for(dim, policy),
            ci_low=mr.ci_low, ci_high=mr.ci_high, sample_size=mr.sample_size,
        ))

    agg = aggregate_risk(risks)
    kri_alerts = evaluate_kris(use_case, assessments, policy, history)

    # --- G5: disposition (gate preserved; trend feeds the Amber branch) ------------------
    gate = audit.scores.failed
    gated_dp = policy.dimensions.get(audit.scores.gated_by) if audit.scores.gated_by else None
    gate_impact = gated_dp.impact if gated_dp else (5 if gate else 0)
    governing = max(assessments, key=lambda a: (a.risk if a.risk is not None else -1), default=None)
    disposition = decide(DispositionInputs(
        gate=gate,
        gate_impact=gate_impact,
        worst_band=worst_band(banded),
        all_green=bool(banded) and all(b is Band.GREEN for b in banded),
        evidence_complete=evidence_complete,
        sign_off_2lod=sign_off_2lod,
        trend_worsening=bool(governing and governing.trend is Trend.UP),
    ))

    # Header stripe/objective from the highest-impact assessed dimension (unless overridden).
    header = max(assessments, key=lambda a: a.impact, default=None)
    header_dp = policy.dimensions.get(header.dimension) if header else None
    record_id = f"AR-{now.strftime('%Y%m%d-%H%M%S')}-{use_case or 'run'}"

    return AssuranceRecord(
        # --- inherited AuditRecord payload (unchanged) ---
        mode=audit.mode, task=audit.task, question=audit.question, response=audit.response,
        rubric=audit.rubric, verdicts=audit.verdicts, scores=audit.scores,
        weight_config=audit.weight_config, prompt_version=audit.prompt_version,
        iteration=audit.iteration, provenance=audit.provenance, yes_rate_summary=audit.yes_rate_summary,
        # --- governance additions ---
        use_case=use_case,
        atlas_stripe=atlas_stripe if atlas_stripe is not None else (header_dp.atlas_stripe if header_dp else ""),
        control_objective=control_objective if control_objective is not None else (header_dp.control_objective if header_dp else ""),
        dimensions=assessments,
        aggregate_risk=agg,
        disposition=disposition,
        evidence_links=evidence_links,
        reviewers=reviewers,
        attestation=attestation,
        overrides=[],
        coverage_scope=default_coverage_scope(),
        kri_alerts=kri_alerts,
        evaluator_reliability=reliability,
        record_id=record_id,
        produced_at=stamp,
        retention_until=retention.date().isoformat(),
        risk_policy_version=policy.policy_version,
    )
