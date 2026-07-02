"""Layer A integration on the deterministic fixture provider (spec §11 gate).

End-to-end with no network and no LLM: the §5 fork/join pipeline runs a fixture provider
plus the real EvaluatorRouter wired to the DeterministicScorer, aggregates via the §7
mapping, and persists a replayable AuditRecord. This is the "tiny fixture provider before
any real adapter" integration test §11 mandates.
"""

from __future__ import annotations

import asyncio
import math

from aah.contracts import Dimension, EvalMethod, Mode, Subtype
from aah.layer_a.aggregator import aggregate
from aah.layer_a.audit import AuditLog
from aah.layer_a.pipeline import run_once
from aah.layer_a.providers import FixtureProvider
from aah.layer_a.providers.base import ProviderAdapter
from aah.layer_a.question_gen import StubQuestionGenerator
from aah.layer_a.router import default_router
from aah.layer_a.rubric_gen import StubRubricGenerator
from tests.conftest import make_question


class _CyclingProvider(ProviderAdapter):
    """Returns each canned response in turn -- to exercise the §9 2-run averaging guard."""

    name = "cycling"

    def __init__(self, responses):
        self._responses = list(responses)
        self._i = 0

    async def query(self, question: str) -> str:
        r = self._responses[self._i % len(self._responses)]
        self._i += 1
        return r


def _deterministic_rubric():
    # Two MAJOR correctness checks (one passes, one fails) + one MINOR format check (passes).
    def q(qid, dim, check):
        base = make_question(qid, dim, eval_method=EvalMethod.DETERMINISTIC,
                             subtype=Subtype.OTHER)
        return base.model_copy(update={"violation_example": check})

    return [
        q("ac_paris", Dimension.ANSWER_CORRECTNESS, "CHECK:contains=Paris"),
        q("ac_berlin", Dimension.ANSWER_CORRECTNESS, "CHECK:contains=Berlin"),
        q("fmt_json", Dimension.INSTRUCTION_FOLLOWING, "CHECK:json_valid"),
    ]


def test_fixture_pipeline_end_to_end(tmp_path):
    response = '{"capital": "Paris"}'
    rubric = _deterministic_rubric()

    record = asyncio.run(
        run_once(
            seed="What is the capital of France? Answer as JSON.",
            p_q="P_Q v0",
            mode=Mode.QUALITY,
            generator=StubQuestionGenerator(),
            provider=FixtureProvider(default=response),
            rubric_gen=StubRubricGenerator(rubric),
            router=default_router(),  # deterministic scorer needs no client
        )
    )

    scores = {v.question_id: v.score for v in record.verdicts}
    assert scores == {"ac_paris": 1, "ac_berlin": 0, "fmt_json": 1}

    # ANSWER_CORRECTNESS (MAJOR, 2/3) mean 0.5; INSTRUCTION_FOLLOWING (MINOR, 1/3) mean 1.0.
    assert math.isclose(record.scores.overall, 2 / 3 * 0.5 + 1 / 3 * 1.0, abs_tol=1e-9)
    assert not record.scores.failed

    # Persist and replay: the stored WeightConfig reproduces the overall score (§7.6).
    log = AuditLog(tmp_path / "runs.jsonl")
    log.append(record)
    (loaded,) = log.read_all()
    replay = aggregate(loaded.verdicts, loaded.rubric, loaded.weight_config)
    assert replay.overall == record.scores.overall


def test_two_run_averaging_resolves_a_flip():
    # Run 1 answers "Paris" (check passes), run 2 answers "Berlin" (check fails) -> the
    # CHECK:contains=Paris question flips and the §9 guard resolves it conservatively to 0.
    rubric = [
        make_question("ac_paris", Dimension.ANSWER_CORRECTNESS,
                      eval_method=EvalMethod.DETERMINISTIC).model_copy(
            update={"violation_example": "CHECK:contains=Paris"})
    ]
    record = asyncio.run(
        run_once(
            seed="capital of France?",
            p_q="P_Q v0",
            mode=Mode.QUALITY,
            generator=StubQuestionGenerator(),
            provider=_CyclingProvider(["Paris", "Berlin"]),
            rubric_gen=StubRubricGenerator(rubric),
            router=default_router(),
            runs=2,
        )
    )
    (verdict,) = record.verdicts
    assert verdict.score == 0
    assert "unstable" in verdict.explanation
