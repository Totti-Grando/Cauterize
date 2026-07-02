"""Skeleton end-to-end run on stub modules (spec §5 shape, M0 gate)."""

from __future__ import annotations

import asyncio

from aah.contracts import Dimension, Mode
from aah.layer_a.pipeline import run_once
from aah.layer_a.providers import FixtureProvider
from aah.layer_a.question_gen import StubQuestionGenerator
from aah.layer_a.router import StubEvaluatorRouter
from aah.layer_a.rubric_gen import StubRubricGenerator
from tests.conftest import make_question


def test_skeleton_runs_end_to_end():
    rubric = [
        make_question("fc1", Dimension.FACTUAL_CONSISTENCY),
        make_question("cp1", Dimension.COMPLETENESS),
    ]
    record = asyncio.run(
        run_once(
            seed="summarize the source",
            p_q="P_Q v0",
            mode=Mode.QUALITY,
            generator=StubQuestionGenerator(),
            provider=FixtureProvider(default="a response"),
            rubric_gen=StubRubricGenerator(rubric),
            router=StubEvaluatorRouter(score=1),
        )
    )
    assert record.question == "summarize the source"
    assert record.response == "a response"
    assert len(record.verdicts) == 2
    assert record.scores.overall == 1.0
    assert not record.scores.failed
    # The full WeightConfig travels with the record (§7.6).
    assert record.weight_config.version == "v0"
