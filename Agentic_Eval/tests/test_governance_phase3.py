"""Layer C Phase 3 (G6–G10): monitoring/trend/KRIs, 3LoD/2LoD, anchors, KPIs, evidence store."""

from __future__ import annotations

import pytest

from aah.config import default_risk_policy, default_weight_config
from aah.contracts import (
    AgentInfo,
    AuditRecord,
    Band,
    Dimension,
    Disposition,
    Mode,
    Provenance,
)
from aah.layer_a.aggregator import aggregate
from aah.layer_c import (
    AssuranceStore,
    ImmutableViolation,
    MonitoringStore,
    governance_template,
    program_kpis,
    to_assurance_record,
)
from tests.conftest import make_question, make_verdict


def _audit(dim: Dimension, scores: list[int], *, provenance: Provenance | None = None) -> AuditRecord:
    rubric = [make_question(f"q{i}", dim) for i in range(len(scores))]
    verdicts = [make_verdict(f"q{i}", s) for i, s in enumerate(scores)]
    cfg = default_weight_config()
    kw = {"provenance": provenance} if provenance is not None else {}
    return AuditRecord(mode=Mode.QUALITY, task="t", question="q", response="r",
                       rubric=rubric, verdicts=verdicts, scores=aggregate(verdicts, rubric, cfg),
                       weight_config=cfg, prompt_version="P", **kw)


# --- G8 anchors + G10 record id ----------------------------------------------------
def test_anchors_and_record_id_are_stamped():
    rec = to_assurance_record(_audit(Dimension.ANSWER_CORRECTNESS, [1]), default_risk_policy(),
                              use_case="uc")
    assert rec.record_id.startswith("AR-")
    assert rec.dimensions[0].anchors  # framework anchors travel in the record


# --- G6 monitoring: trend + KRI ----------------------------------------------------
def test_worsening_trend_pushes_amber_to_remediate():
    policy, hist = default_risk_policy(), MonitoringStore()
    # unsupported_claim_rate stays in Amber (green<=0.02, amber<=0.05) but worsens 3% -> 5%
    # (delta 0.02 >= the trend epsilon), so the trend arrow reads "up".
    a1 = _audit(Dimension.FACTUAL_CONSISTENCY, [1] * 97 + [0] * 3)   # 3% -> Amber
    r1 = to_assurance_record(a1, policy, use_case="uc", history=hist)
    assert r1.dimensions[0].band is Band.AMBER
    a2 = _audit(Dimension.FACTUAL_CONSISTENCY, [1] * 95 + [0] * 5)   # 5% -> Amber, worse
    r2 = to_assurance_record(a2, policy, use_case="uc", history=hist)
    assert r2.dimensions[0].trend.value == "up"
    assert r2.disposition is Disposition.REMEDIATE   # worsening Amber -> Remediate


def test_red_band_raises_reevaluation_kri():
    a = _audit(Dimension.FACTUAL_CONSISTENCY, [0, 0, 1])            # 67% unsupported -> Red
    rec = to_assurance_record(a, default_risk_policy(), use_case="uc")
    assert rec.dimensions[0].band is Band.RED
    assert any(k.kri == "band_red" and k.reevaluate for k in rec.kri_alerts)


# --- G7 3LoD / 2LoD challenge ------------------------------------------------------
def _prov(same_family: bool) -> Provenance:
    return Provenance(
        evaluator=AgentInfo(backend="anthropic", model="claude"),
        provider=AgentInfo(backend="groq", model="llama"),
        same_family_judge=same_family,
    )


def test_cross_family_run_auto_clears_2lod():
    a = _audit(Dimension.ANSWER_CORRECTNESS, [1, 1, 1], provenance=_prov(same_family=False))
    rec = to_assurance_record(a, default_risk_policy(), use_case="uc", evidence_complete=True)
    # a cross-family reference judged the run -> 2LoD auto-cleared -> Approve
    assert any(r.lod.value == "second" for r in rec.reviewers)
    assert rec.disposition is Disposition.APPROVE


def test_same_family_run_does_not_auto_clear_2lod():
    a = _audit(Dimension.ANSWER_CORRECTNESS, [1, 1, 1], provenance=_prov(same_family=True))
    rec = to_assurance_record(a, default_risk_policy(), use_case="uc", evidence_complete=True)
    assert not any(r.lod.value == "second" for r in rec.reviewers)
    assert rec.disposition is Disposition.APPROVE_WITH_CONDITIONS


# --- G9 program KPIs ---------------------------------------------------------------
def test_program_kpis_rollup():
    policy = default_risk_policy()
    good = to_assurance_record(_audit(Dimension.ANSWER_CORRECTNESS, [1, 1], provenance=_prov(False)),
                               policy, use_case="a", evidence_complete=True)
    bad = to_assurance_record(_audit(Dimension.INJECTION_RESISTANCE, [0]), policy, use_case="b")
    k = program_kpis([good, bad])
    assert k.total_records == 2
    assert k.decision_quality == 1.0                 # both carry a disposition
    assert 0.0 < k.challenge_rate_2lod <= 1.0        # one has a 2LoD challenge


# --- G10 immutable evidence store + export -----------------------------------------
def test_evidence_store_is_write_once(tmp_path):
    store = AssuranceStore(tmp_path / "assurance.jsonl")
    rec = to_assurance_record(_audit(Dimension.ANSWER_CORRECTNESS, [1]), default_risk_policy(),
                              use_case="uc", produced_at=__import__("datetime").datetime(2026, 7, 8, 9, 0, 0))
    rid = store.put(rec)
    assert store.exists(rid)
    with pytest.raises(ImmutableViolation):
        store.put(rec)                               # cannot overwrite an existing record


def test_governance_template_has_expected_fields():
    rec = to_assurance_record(_audit(Dimension.FACTUAL_CONSISTENCY, [1]), default_risk_policy(),
                              use_case="uc")
    tpl = governance_template(rec)
    for key in ("use_case", "atlas_stripe", "dimensions", "aggregate_risk", "disposition",
                "reviewers", "attestation", "coverage_scope", "retention_until"):
        assert key in tpl
    assert tpl["dimensions"][0]["metric_id"]
    assert tpl["coverage_scope"]["out_of_scope"] == ["operational_resilience"]
