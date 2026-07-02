"""F1: every emitted AuditRecord records WHO judged and WHO was judged (provenance)."""

from __future__ import annotations

from aah.contracts import AgentInfo, Dimension, EvalMethod, Mode
from aah.layer_a.pipeline import run_once
from aah.layer_a.providers import FixtureProvider
from aah.layer_a.question_gen import StubQuestionGenerator
from aah.layer_a.router import default_router
from aah.layer_a.rubric_gen import StubRubricGenerator
from tests.conftest import make_question


def _rubric():
    q = make_question("c", Dimension.ANSWER_CORRECTNESS, eval_method=EvalMethod.DETERMINISTIC)
    return [q.model_copy(update={"check_directive": "CHECK:contains=paris"})]


async def test_record_always_has_non_null_evaluator_and_provider_model():
    record = await run_once(
        seed="capital of France?", p_q="P_Q", mode=Mode.QUALITY,
        generator=StubQuestionGenerator(),
        provider=FixtureProvider(default="Paris"),
        rubric_gen=StubRubricGenerator(_rubric()),
        router=default_router(),
    )
    assert record.provenance.evaluator.model  # non-empty
    assert record.provenance.provider.model   # non-empty
    assert record.schema_version == "v1"


async def test_explicit_provenance_is_recorded():
    record = await run_once(
        seed="q", p_q="P_Q", mode=Mode.QUALITY,
        generator=StubQuestionGenerator(),
        provider=FixtureProvider(default="Paris"),
        rubric_gen=StubRubricGenerator(_rubric()),
        router=default_router(),
        evaluator=AgentInfo(backend="bedrock", model="anthropic.claude-opus-4-8"),
        provider_info=AgentInfo(backend="http", model="ravenpack-v2"),
    )
    assert record.provenance.evaluator.model == "anthropic.claude-opus-4-8"
    assert record.provenance.provider.model == "ravenpack-v2"


async def test_same_verdicts_different_evaluator_are_distinguishable():
    kwargs = dict(
        seed="q", p_q="P_Q", mode=Mode.QUALITY,
        generator=StubQuestionGenerator(),
        provider=FixtureProvider(default="Paris"),
        rubric_gen=StubRubricGenerator(_rubric()),
        router=default_router(),
        provider_info=AgentInfo(backend="http", model="ravenpack-v2"),
    )
    a = await run_once(**kwargs, evaluator=AgentInfo(backend="groq", model="llama-3.3-70b"))
    b = await run_once(**kwargs, evaluator=AgentInfo(backend="bedrock", model="claude-opus-4-8"))
    # Identical verdicts...
    assert [v.score for v in a.verdicts] == [v.score for v in b.verdicts]
    # ...but distinguishable by who judged.
    assert a.provenance.evaluator.model != b.provenance.evaluator.model
    assert a != b
