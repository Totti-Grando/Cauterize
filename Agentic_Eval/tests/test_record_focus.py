"""R7: the AuditRecord stamps the focus profile + effective weights, and a no-focus run still
validates (backward compatible)."""

from __future__ import annotations

from aah.config import default_weight_config
from aah.contracts import AuditRecord, Dimension, Mode, Provenance, AgentInfo
from aah.layer_a.aggregator import aggregate, effective_weights_of, focus_profile
from tests.conftest import make_question, make_verdict


def _record(cfg):
    rubric = [make_question("r1", Dimension.RELEVANCE), make_question("g1", Dimension.FACTUAL_CONSISTENCY)]
    verdicts = [make_verdict("r1", 1), make_verdict("g1", 1)]
    scores = aggregate(verdicts, rubric, cfg)
    return AuditRecord(
        mode=Mode.QUALITY, task="t", question="q", response="a",
        rubric=rubric, verdicts=verdicts, scores=scores, weight_config=cfg,
        prompt_version="P_Q@v1",
        provenance=Provenance(evaluator=AgentInfo(model="m"), provider=AgentInfo(model="p")),
        focus=focus_profile(cfg),
        effective_weights=effective_weights_of(scores),
    )


def test_focus_run_stamps_profile_and_weights():
    cfg = default_weight_config(focus=["relevance"], focus_boost=2.0)
    rec = _record(cfg)
    assert rec.focus == ["relevance"]
    # relevance is boosted -> its effective weight exceeds the un-boosted grounding dim
    assert rec.effective_weights["relevance"] > rec.effective_weights["factual_consistency"]
    assert rec.schema_version == "v1.1"


def test_effective_weights_mirror_scores():
    cfg = default_weight_config(focus=["relevance"])
    rec = _record(cfg)
    from_scores = {d.dimension.value: d.weight for d in rec.scores.per_dimension if not d.abstained and d.weight > 0}
    assert rec.effective_weights == from_scores


def test_no_focus_run_is_backward_compatible():
    rec = _record(default_weight_config())
    assert rec.focus == []
    # weights still present (from tiers) but no focus profile
    assert rec.effective_weights  # non-empty (scored dims)
    assert AuditRecord.model_validate(rec.model_dump()) == rec  # round-trips
