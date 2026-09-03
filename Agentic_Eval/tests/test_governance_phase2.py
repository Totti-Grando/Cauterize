"""Layer C Phase 2 (G3–G5): metric adapters, G/A/R + L×I banding, and the disposition engine."""

from __future__ import annotations

import pytest

from aah.config import default_risk_policy, default_weight_config
from aah.contracts import AuditRecord, Band, Dimension, Disposition, GarBands, Mode
from aah.layer_a.aggregator import aggregate
from aah.layer_c import to_assurance_record
from aah.layer_c.banding import aggregate_risk, band_for, likelihood_for, risk_of
from aah.layer_c.disposition import DispositionInputs, decide
from aah.layer_c.metrics import compute_metrics
from tests.conftest import make_question, make_verdict


# --- G4 banding units --------------------------------------------------------------
def test_band_for_lower_is_better_boundaries():
    b = GarBands(direction="lower_is_better", green=0.02, amber=0.05)
    assert band_for(0.02, b) is Band.GREEN     # inclusive green edge
    assert band_for(0.05, b) is Band.AMBER     # inclusive amber edge
    assert band_for(0.051, b) is Band.RED


def test_band_for_higher_is_better_boundaries():
    b = GarBands(direction="higher_is_better", green=0.9, amber=0.75)
    assert band_for(0.9, b) is Band.GREEN
    assert band_for(0.75, b) is Band.AMBER
    assert band_for(0.74, b) is Band.RED


def test_zero_tolerance_has_no_amber():
    zt = GarBands(direction="lower_is_better", green=0.0, amber=None, zero_tolerance=True)
    assert band_for(0.0, zt) is Band.GREEN
    assert band_for(0.0001, zt) is Band.RED    # any non-zero incident -> Red


def test_likelihood_and_risk():
    assert likelihood_for(Band.GREEN) == 1
    assert likelihood_for(Band.AMBER) == 3
    assert likelihood_for(Band.RED) == 5
    assert risk_of(Band.RED, 5) == 25          # worst case = 25


def test_aggregate_is_max_and_mean():
    agg = aggregate_risk([4, 20, 8])
    assert agg.max == 20                        # governing
    assert agg.mean == pytest.approx(10.667, abs=1e-3)  # portfolio
    empty = aggregate_risk([])
    assert empty.max is None and empty.mean is None


# --- G3 metric adapters ------------------------------------------------------------
def _audit(dim: Dimension, scores: list[int]) -> AuditRecord:
    rubric = [make_question(f"q{i}", dim) for i in range(len(scores))]
    verdicts = [make_verdict(f"q{i}", s) for i, s in enumerate(scores)]
    cfg = default_weight_config()
    return AuditRecord(mode=Mode.QUALITY, task="t", question="q", response="r",
                       rubric=rubric, verdicts=verdicts, scores=aggregate(verdicts, rubric, cfg),
                       weight_config=cfg, prompt_version="P")


def test_pass_rate_metric_for_higher_is_better_dimension():
    m = compute_metrics(_audit(Dimension.ANSWER_CORRECTNESS, [1, 1, 0, 1]), default_risk_policy())
    assert m[Dimension.ANSWER_CORRECTNESS].value == pytest.approx(0.75)  # 3/4 pass


def test_failure_rate_metric_for_lower_is_better_dimension():
    m = compute_metrics(_audit(Dimension.FACTUAL_CONSISTENCY, [1, 0, 1, 1]), default_risk_policy())
    assert m[Dimension.FACTUAL_CONSISTENCY].value == pytest.approx(0.25)  # 1/4 unsupported


def test_fairness_abstains_without_cohorts():
    m = compute_metrics(_audit(Dimension.SAFETY_FAIRNESS, [1, 0]), default_risk_policy())
    res = m[Dimension.SAFETY_FAIRNESS]
    assert res.value is None and res.abstained and "cohort" in res.reason


def test_robustness_abstains_without_repeats():
    m = compute_metrics(_audit(Dimension.ROBUSTNESS, [1, 0]), default_risk_policy())
    assert m[Dimension.ROBUSTNESS].abstained


# --- G5 disposition table ----------------------------------------------------------
def _inp(**kw) -> DispositionInputs:
    base = dict(gate=False, gate_impact=0, worst_band=Band.GREEN, all_green=True,
                evidence_complete=True, sign_off_2lod=True, trend_worsening=False)
    base.update(kw)
    return DispositionInputs(**base)


def test_gate_forces_escalate_or_remediate_never_approve():
    assert decide(_inp(gate=True, gate_impact=5)) is Disposition.ESCALATE
    assert decide(_inp(gate=True, gate_impact=2)) is Disposition.REMEDIATE
    # Gate dominates even if everything else looks approvable.
    assert decide(_inp(gate=True, gate_impact=3, all_green=True)) is not Disposition.APPROVE


def test_amber_is_conditional_unless_worsening():
    assert decide(_inp(worst_band=Band.AMBER, all_green=False)) is Disposition.APPROVE_WITH_CONDITIONS
    assert decide(_inp(worst_band=Band.AMBER, all_green=False, trend_worsening=True)) is Disposition.REMEDIATE


def test_scored_red_remediates():
    assert decide(_inp(worst_band=Band.RED, all_green=False)) is Disposition.REMEDIATE


def test_all_green_approves_only_with_evidence_and_signoff():
    assert decide(_inp()) is Disposition.APPROVE
    assert decide(_inp(evidence_complete=False)) is Disposition.APPROVE_WITH_CONDITIONS
    assert decide(_inp(sign_off_2lod=False)) is Disposition.APPROVE_WITH_CONDITIONS


# --- end to end through to_assurance_record ----------------------------------------
def test_green_run_approves_with_evidence_and_signoff():
    rec = to_assurance_record(_audit(Dimension.ANSWER_CORRECTNESS, [1, 1, 1]), default_risk_policy(),
                              use_case="uc", evidence_complete=True, sign_off_2lod=True)
    assert rec.disposition is Disposition.APPROVE
    assert rec.aggregate_risk.max is not None


def test_green_run_without_evidence_is_conditional():
    rec = to_assurance_record(_audit(Dimension.ANSWER_CORRECTNESS, [1, 1, 1]), default_risk_policy(),
                              use_case="uc")
    assert rec.disposition is Disposition.APPROVE_WITH_CONDITIONS
