"""AuditRecord JSONL round-trip + score replay (spec §7.6)."""

from __future__ import annotations

from aah.config import default_weight_config
from aah.contracts import AuditRecord, Dimension, Mode
from aah.layer_a.aggregator import aggregate
from aah.layer_a.audit import AuditLog
from tests.conftest import make_question, make_verdict


def _record() -> AuditRecord:
    rubric = [make_question("fc1", Dimension.FACTUAL_CONSISTENCY)]
    verdicts = [make_verdict("fc1", 1)]
    cfg = default_weight_config()
    scores = aggregate(verdicts, rubric, cfg)
    return AuditRecord(
        mode=Mode.QUALITY, task="t", question="q", response="r",
        rubric=rubric, verdicts=verdicts, scores=scores,
        weight_config=cfg, prompt_version="P_Q@v0",
    )


def test_jsonl_round_trip(tmp_path):
    log = AuditLog(tmp_path / "runs.jsonl")
    rec = _record()
    log.append(rec)
    (loaded,) = log.read_all()
    assert loaded.model_dump() == rec.model_dump()


def test_stored_config_replays_score(tmp_path):
    log = AuditLog(tmp_path / "runs.jsonl")
    log.append(_record())
    (loaded,) = log.read_all()
    # Re-score from the persisted record alone -> identical overall.
    replay = aggregate(loaded.verdicts, loaded.rubric, loaded.weight_config)
    assert replay.overall == loaded.scores.overall
