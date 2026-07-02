"""F5: per-dimension gate threshold + gating run-count are explicit, tuned policy."""

from __future__ import annotations

from aah.config import default_weight_config
from aah.contracts import Dimension, EvalMethod, Mode, Verdict
from aah.layer_a.aggregator import aggregate
from aah.layer_a.pipeline import run_once
from aah.layer_a.providers import FixtureProvider
from aah.layer_a.question_gen import StubQuestionGenerator
from aah.layer_a.router import default_router
from aah.layer_a.rubric_gen import StubRubricGenerator
from tests.conftest import make_question

_CRIT = Dimension.DATA_LEAKAGE  # a CRITICAL gating dimension


def _two_gating_checks(must_pass_second=False):
    a = make_question("a", _CRIT, eval_method=EvalMethod.DETERMINISTIC)
    b = make_question("b", _CRIT, eval_method=EvalMethod.DETERMINISTIC, must_pass=must_pass_second)
    return [a, b]


def _verdicts(pass_a=1, pass_b=0):
    return [
        Verdict(question_id="a", score=pass_a, explanation="x"),
        Verdict(question_id="b", score=pass_b, explanation="x"),
    ]


def test_single_flip_does_not_fail_when_threshold_below_one():
    rubric = _two_gating_checks()
    cfg = default_weight_config().model_copy(update={"gate_thresholds": {_CRIT: 0.5}})
    scores = aggregate(_verdicts(1, 0), rubric, cfg)  # dimension score = 0.5
    assert scores.failed is False  # 0.5 is not < 0.5 → absorbs the single false positive


def test_single_flip_fails_at_default_threshold():
    rubric = _two_gating_checks()
    cfg = default_weight_config()  # threshold 1.0
    scores = aggregate(_verdicts(1, 0), rubric, cfg)
    assert scores.failed is True and scores.gated_by is _CRIT


def test_must_pass_flip_always_fails_regardless_of_threshold():
    rubric = _two_gating_checks(must_pass_second=True)
    cfg = default_weight_config().model_copy(update={"gate_thresholds": {_CRIT: 0.0}})
    scores = aggregate(_verdicts(1, 0), rubric, cfg)  # b is must_pass and scored 0
    assert scores.failed is True and scores.gated_by is _CRIT


class _CountingProvider(FixtureProvider):
    def __init__(self, default):
        super().__init__(default=default)
        self.n = 0

    async def query(self, question: str) -> str:
        self.n += 1
        return await super().query(question)


async def test_gating_rubric_runs_at_least_min_runs():
    rubric = [make_question("c", _CRIT, eval_method=EvalMethod.DETERMINISTIC).model_copy(
        update={"check_directive": "CHECK:contains=safe"})]
    provider = _CountingProvider("this is a safe answer")
    await run_once(
        seed="q", p_q="P", mode=Mode.QUALITY, generator=StubQuestionGenerator(),
        provider=provider, rubric_gen=StubRubricGenerator(rubric), router=default_router(), runs=1,
    )
    assert provider.n >= 2  # gating_min_runs default


async def test_nongating_rubric_runs_once():
    rubric = [make_question("c", Dimension.COMPLETENESS, eval_method=EvalMethod.DETERMINISTIC).model_copy(
        update={"check_directive": "CHECK:contains=safe"})]
    provider = _CountingProvider("this is a safe answer")
    await run_once(
        seed="q", p_q="P", mode=Mode.QUALITY, generator=StubQuestionGenerator(),
        provider=provider, rubric_gen=StubRubricGenerator(rubric), router=default_router(), runs=1,
    )
    assert provider.n == 1
