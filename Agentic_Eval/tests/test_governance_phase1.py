"""Layer C governance wrap: gate preservation, retention, and the G16 scope boundary."""

from __future__ import annotations

from datetime import date, datetime

from aah.config import default_risk_policy, default_weight_config
from aah.contracts import AuditRecord, Band, Dimension, Disposition, Mode
from aah.layer_a.aggregator import aggregate
from aah.layer_c import to_assurance_record
from tests.conftest import make_question, make_verdict


def _audit(dimension: Dimension, score: int, *, must_pass: bool = False) -> AuditRecord:
    rubric = [make_question("q1", dimension, must_pass=must_pass)]
    verdicts = [make_verdict("q1", score)]
    cfg = default_weight_config()
    return AuditRecord(
        mode=Mode.QUALITY, task="t", question="q", response="r",
        rubric=rubric, verdicts=verdicts, scores=aggregate(verdicts, rubric, cfg),
        weight_config=cfg, prompt_version="P_Q@v0",
    )


def test_gated_critical_run_escalates_never_approve():
    # A CRITICAL dimension (impact 5) scoring 0 gates the run -> Escalate, and never Approve.
    audit = _audit(Dimension.INJECTION_RESISTANCE, 0)
    assert audit.scores.failed
    rec = to_assurance_record(audit, default_risk_policy(), use_case="uc")
    assert rec.disposition is Disposition.ESCALATE
    assert rec.disposition is not Disposition.APPROVE


def test_gated_must_pass_minor_remediates():
    # A must-pass failure on a MINOR dimension (impact 2) gates -> Remediate (not top-impact escalate).
    audit = _audit(Dimension.INSTRUCTION_FOLLOWING, 0, must_pass=True)
    assert audit.scores.failed
    rec = to_assurance_record(audit, default_risk_policy(), use_case="uc")
    assert rec.disposition is Disposition.REMEDIATE
    assert rec.disposition is not Disposition.APPROVE


def test_retention_is_at_least_seven_years():
    produced = datetime(2026, 7, 8, 12, 0, 0)
    rec = to_assurance_record(_audit(Dimension.ANSWER_CORRECTNESS, 1), default_risk_policy(),
                              use_case="uc", produced_at=produced)
    assert rec.produced_at.startswith("2026-07-08")
    retention = date.fromisoformat(rec.retention_until)
    assert (retention - produced.date()).days >= 7 * 365


def test_coverage_marks_resilience_out_of_scope_and_makes_no_resilience_claim():
    rec = to_assurance_record(_audit(Dimension.ANSWER_CORRECTNESS, 1), default_risk_policy(),
                              use_case="uc")
    scope = rec.coverage_scope
    assert "operational_resilience" in scope.out_of_scope
    assert "operational_resilience" not in scope.in_scope
    assert all("resilience" not in a.dim_id.lower() for a in rec.dimensions)


def test_dimension_assessments_are_banded():
    # factual_consistency with a passing verdict -> failure_rate 0.0 -> GREEN (lower_is_better).
    rec = to_assurance_record(_audit(Dimension.FACTUAL_CONSISTENCY, 1), default_risk_policy(),
                              use_case="uc")
    a = rec.dimensions[0]
    assert a.dim_id and a.metric_id
    assert a.metric_value == 0.0
    assert a.band is Band.GREEN
    assert a.likelihood == 1
    assert a.risk == a.likelihood * a.impact
