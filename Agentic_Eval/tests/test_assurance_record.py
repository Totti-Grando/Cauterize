"""Layer C G2: AssuranceRecord extends AuditRecord (version-bumped, backward compatible)."""

from __future__ import annotations

from aah.config import default_risk_policy, default_weight_config
from aah.contracts import AssuranceRecord, AuditRecord, Dimension, Mode
from aah.layer_a.aggregator import aggregate
from aah.layer_c import to_assurance_record
from tests.conftest import make_question, make_verdict


def _audit(dimension: Dimension = Dimension.FACTUAL_CONSISTENCY, score: int = 1) -> AuditRecord:
    rubric = [make_question("q1", dimension)]
    verdicts = [make_verdict("q1", score)]
    cfg = default_weight_config()
    scores = aggregate(verdicts, rubric, cfg)
    return AuditRecord(
        mode=Mode.QUALITY, task="t", question="q", response="r",
        rubric=rubric, verdicts=verdicts, scores=scores,
        weight_config=cfg, prompt_version="P_Q@v0",
    )


def test_assurance_record_is_an_audit_record_subclass():
    rec = to_assurance_record(_audit(), default_risk_policy(), use_case="uc-1")
    assert isinstance(rec, AuditRecord)          # validates as both
    assert rec.schema_version == "v2"            # version bumped
    assert rec.use_case == "uc-1"
    # one assessment per scored dimension present in the run, carrying its ids from the policy
    assert rec.dimensions and rec.dimensions[0].dim_id and rec.dimensions[0].metric_id


def test_assurance_record_jsonl_round_trip():
    rec = to_assurance_record(_audit(), default_risk_policy(), use_case="uc-1")
    dumped = rec.model_dump_json()
    loaded = AssuranceRecord.model_validate_json(dumped)
    assert loaded.model_dump() == rec.model_dump()


def test_legacy_audit_record_still_valid_and_v1():
    # A plain AuditRecord still constructs; schema is v1.1 (focus fields added additively, R7).
    audit = _audit()
    assert isinstance(audit, AuditRecord)
    assert audit.schema_version == "v1.1"
    # ...and it carries none of the governance fields.
    assert "disposition" not in audit.model_dump()
    # legacy / no-focus run still validates with empty focus + weights
    assert audit.focus == []
    assert audit.effective_weights == {}
