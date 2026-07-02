"""Offline tests for the A4 EvaluatorRouter (spec §6 router).

Builds a RealEvaluatorRouter from stub scorers and asserts each EvalMethod routes to the
right scorer; an unmapped method raises.
"""

from __future__ import annotations

import asyncio

import pytest

from aah.contracts import BinaryQuestion, Dimension, EvalMethod, Subtype, Verdict
from aah.layer_a.router import RealEvaluatorRouter, default_router


def make_question(qid: str, eval_method: EvalMethod) -> BinaryQuestion:
    return BinaryQuestion(
        id=qid,
        requirement_id=f"req-{qid}",
        dimension=Dimension.FACTUAL_CONSISTENCY,
        subtype=Subtype.OTHER,
        text=f"question {qid}",
        violation_example="example",
        eval_method=eval_method,
    )


class TaggedScorer:
    """A stub scorer that stamps its tag into the verdict explanation."""

    def __init__(self, tag: str):
        self.tag = tag

    async def score(self, question, response, context) -> Verdict:
        return Verdict(question_id=question.id, score=1, explanation=f"scored-by:{self.tag}")


def test_router_dispatches_each_eval_method_to_its_scorer():
    scorers = {method: TaggedScorer(method.value) for method in EvalMethod}
    router = RealEvaluatorRouter(scorers)
    for method in EvalMethod:
        q = make_question(f"q-{method.value}", method)
        v = asyncio.run(router.score(q, "resp", "ctx"))
        assert v.explanation == f"scored-by:{method.value}"
        assert v.question_id == q.id


def test_router_unmapped_method_raises():
    # Only DETERMINISTIC is registered; routing an NLI question must raise.
    router = RealEvaluatorRouter({EvalMethod.DETERMINISTIC: TaggedScorer("det")})
    q = make_question("q-nli", EvalMethod.NLI)
    with pytest.raises(KeyError):
        asyncio.run(router.score(q, "resp", "ctx"))


def test_default_router_wires_all_five_methods():
    # No client / fetcher needed just to wire the mapping (nothing is called).
    router = default_router()
    assert set(router._scorers.keys()) == set(EvalMethod)


def test_default_router_routes_deterministic_offline():
    # The deterministic scorer needs no LLM, so the default router runs fully offline.
    router = default_router()
    q = BinaryQuestion(
        id="d1",
        requirement_id="req-d1",
        dimension=Dimension.INSTRUCTION_FOLLOWING,
        subtype=Subtype.OTHER,
        text="is the output valid JSON?",
        violation_example="CHECK:json_valid",
        eval_method=EvalMethod.DETERMINISTIC,
    )
    ok = asyncio.run(router.score(q, '{"k": 1}', ""))
    assert ok.score == 1
    bad = asyncio.run(router.score(q, "not json", ""))
    assert bad.score == 0
