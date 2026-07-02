"""F4: self-enhancement-bias controls — same-family flag + cross-family reference / panel gates."""

from __future__ import annotations

from aah.contracts import AgentInfo, Dimension, EvalMethod, Mode
from aah.layer_a.pipeline import run_once
from aah.layer_a.providers import FixtureProvider
from aah.layer_a.question_gen import StubQuestionGenerator
from aah.layer_a.router import StubEvaluatorRouter, default_router
from aah.layer_a.rubric_gen import StubRubricGenerator
from tests.conftest import make_question

_GATE = Dimension.DATA_LEAKAGE
_SOFT = Dimension.COMPLETENESS


def _rubric():
    return [
        make_question("g", _GATE, eval_method=EvalMethod.DETERMINISTIC),
        make_question("s", _SOFT, eval_method=EvalMethod.DETERMINISTIC),
    ]


async def _run(**kw):
    return await run_once(
        seed="q", p_q="P", mode=Mode.QUALITY, generator=StubQuestionGenerator(),
        provider=FixtureProvider(default="answer"),
        rubric_gen=StubRubricGenerator(_rubric()), **kw,
    )


async def test_same_family_flag_true_and_false():
    same = await _run(
        router=default_router(),
        evaluator=AgentInfo(backend="bedrock", model="claude-opus-4-8"),
        provider_info=AgentInfo(backend="anthropic", model="claude-3-5"),
    )
    assert same.provenance.same_family_judge is True

    cross = await _run(
        router=default_router(),
        evaluator=AgentInfo(backend="bedrock", model="claude-opus-4-8"),
        provider_info=AgentInfo(backend="groq", model="llama-3.3-70b"),
    )
    assert cross.provenance.same_family_judge is False


async def test_gating_checks_routed_to_cross_family_reference():
    # main judge would pass everything (1); the cross-family reference fails gates (0).
    record = await _run(
        router=StubEvaluatorRouter(score=1),
        gating_router=StubEvaluatorRouter(score=0),
    )
    by_id = {v.question_id: v.score for v in record.verdicts}
    assert by_id["g"] == 0  # gating check judged by the cross-family reference
    assert by_id["s"] == 1  # non-gating check judged by the main judge


async def test_judge_panel_fails_gate_if_any_panelist_fails():
    record = await _run(
        router=StubEvaluatorRouter(score=1),
        gating_panel=[StubEvaluatorRouter(score=1), StubEvaluatorRouter(score=0)],
    )
    by_id = {v.question_id: v.score for v in record.verdicts}
    assert by_id["g"] == 0  # any failing panelist fails the gate
    assert by_id["s"] == 1  # soft check untouched by the panel
