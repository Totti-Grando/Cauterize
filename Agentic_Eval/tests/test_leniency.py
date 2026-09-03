"""F6: leniency / yes-bias controls — negative-default framing, yes-rate recorded + flagged."""

from __future__ import annotations

from aah.contracts import Dimension, EvalMethod, Mode
from aah.determinism_guards import flag_lenient_dimensions
from aah.layer_a.pipeline import run_once
from aah.layer_a.providers import FixtureProvider
from aah.layer_a.question_gen import StubQuestionGenerator
from aah.layer_a.router import default_router
from aah.layer_a.rubric_gen import StubRubricGenerator
from aah.layer_a.scorers.llm_judge import _SYSTEM as JUDGE_SYSTEM
from tests.conftest import make_question


def test_judge_prompt_defaults_to_negative():
    low = JUDGE_SYSTEM.lower()
    assert "default to 'no'" in low
    assert "do not reward length" in low


def test_flag_lenient_dimensions():
    summary = {"answer_correctness": 1.0, "completeness": 0.5, "relevance": 0.97}
    flagged = flag_lenient_dimensions(summary, ceiling=0.95)
    assert set(flagged) == {"answer_correctness", "relevance"}


async def test_yes_rate_recorded_and_known_bad_stays_low():
    # A clearly-bad answer against deterministic checks it fails: pass-rate must stay low.
    rubric = [
        make_question("a", Dimension.ANSWER_CORRECTNESS, eval_method=EvalMethod.DETERMINISTIC).model_copy(
            update={"check_directive": "CHECK:contains=Paris"}),
        make_question("b", Dimension.ANSWER_CORRECTNESS, eval_method=EvalMethod.DETERMINISTIC).model_copy(
            update={"check_directive": "CHECK:contains=France"}),
    ]
    record = await run_once(
        seed="capital?", p_q="P", mode=Mode.QUALITY, generator=StubQuestionGenerator(),
        provider=FixtureProvider(default="a wrong, irrelevant answer"),
        rubric_gen=StubRubricGenerator(rubric), router=default_router(),
    )
    assert record.yes_rate_summary  # recorded
    assert record.yes_rate_summary["answer_correctness"] <= 0.5  # bad input isn't inflated
