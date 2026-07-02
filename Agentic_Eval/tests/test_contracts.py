"""Contract invariants (spec §4): mandatory explanation, score bounds, immutability."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from aah.contracts import Dimension, EvalMethod, Subtype, Verdict
from tests.conftest import make_question, make_verdict


def test_verdict_explanation_is_mandatory():
    with pytest.raises(ValidationError):
        Verdict(question_id="q1", score=1, explanation="")  # empty not allowed


def test_verdict_score_is_binary():
    with pytest.raises(ValidationError):
        Verdict(question_id="q1", score=2, explanation="bad")


def test_models_are_frozen():
    v = make_verdict("q1", 1)
    with pytest.raises(ValidationError):
        v.score = 0  # type: ignore[misc]


def test_binary_question_is_born_tagged():
    q = make_question("q1", Dimension.FACTUAL_CONSISTENCY,
                      subtype=Subtype.UNSUPPORTED, eval_method=EvalMethod.NLI)
    assert q.dimension is Dimension.FACTUAL_CONSISTENCY
    assert q.subtype is Subtype.UNSUPPORTED
    assert q.eval_method is EvalMethod.NLI
    assert q.violation_example  # non-empty


def test_extra_fields_forbidden():
    with pytest.raises(ValidationError):
        Verdict(question_id="q1", score=1, explanation="ok", bogus=True)  # type: ignore[call-arg]
