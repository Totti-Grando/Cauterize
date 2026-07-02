"""Offline unit tests for ClaudeRubricGenerator (spec §5 step 3b, §6, §9).

A fake Anthropic client returns canned JSON as ``.content[0].text`` so these tests run
with no API key and no network. They assert: valid born-tagged BinaryQuestions with the
right enum tags + stable ids, the §9 holistic cap on RELEVANCE, and that the LLM call does
NOT pass a temperature (Opus 4.7/4.8 rejects it).
"""

from __future__ import annotations

import json

from aah.contracts import BinaryQuestion, Dimension, EvalMethod, Subtype
from aah.layer_a.rubric_gen import ClaudeRubricGenerator


class _FakeBlock:
    def __init__(self, text: str):
        self.text = text


class _FakeMessage:
    def __init__(self, text: str):
        self.content = [_FakeBlock(text)]


class _FakeMessages:
    def __init__(self, text: str, captured: dict):
        self._text = text
        self._captured = captured

    def create(self, **kwargs):
        self._captured.update(kwargs)
        return _FakeMessage(self._text)


class _FakeAnthropic:
    """Mirrors anthropic.Anthropic(): exposes ``.messages.create(...)``."""

    def __init__(self, text: str):
        self.captured: dict = {}
        self.messages = _FakeMessages(text, self.captured)


def _canned_items() -> list[dict]:
    items = [
        {
            "requirement_text": "The answer must be grounded in the source.",
            "dimension": "factual_consistency",
            "subtype": "unsupported",
            "eval_method": "nli",
            "question_text": "Is every claim supported by the source?",
            "violation_example": "States a fact absent from the source.",
            "must_pass": False,
        },
        {
            "requirement_text": "The answer must be valid JSON.",
            "dimension": "instruction_following",
            "subtype": "other",
            "eval_method": "deterministic",
            "question_text": "Is the output valid JSON?",
            "violation_example": "Returns prose instead of JSON.",
            "must_pass": True,
        },
    ]
    # Five RELEVANCE questions, one of them must_pass=True to exercise the soft-cap.
    for i in range(5):
        items.append(
            {
                "requirement_text": "The answer must stay on topic.",
                "dimension": "relevance",
                "subtype": "other",
                "eval_method": "llm_judge",
                "question_text": f"Does the answer address aspect {i} of the question?",
                "violation_example": "Goes off on an unrelated tangent.",
                "must_pass": i == 0,
            }
        )
    return items


def _make_generator(items, **kwargs):
    fake = _FakeAnthropic(json.dumps(items))
    gen = ClaudeRubricGenerator(client=fake, **kwargs)
    return gen, fake


def test_build_returns_valid_born_tagged_questions():
    gen, _ = _make_generator(_canned_items())
    rubric = gen.build("Summarize the article.", context="Some source text.")

    assert rubric, "expected a non-empty rubric"
    assert all(isinstance(q, BinaryQuestion) for q in rubric)

    # Stable sequential ids.
    assert [q.id for q in rubric] == [f"q{i + 1}" for i in range(len(rubric))]

    by_text = {q.text: q for q in rubric}
    grounded = by_text["Is every claim supported by the source?"]
    assert grounded.dimension is Dimension.FACTUAL_CONSISTENCY
    assert grounded.subtype is Subtype.UNSUPPORTED
    assert grounded.eval_method is EvalMethod.NLI
    assert grounded.violation_example == "States a fact absent from the source."

    json_q = by_text["Is the output valid JSON?"]
    assert json_q.dimension is Dimension.INSTRUCTION_FOLLOWING
    assert json_q.eval_method is EvalMethod.DETERMINISTIC
    assert json_q.must_pass is True  # non-holistic must_pass is preserved

    # Requirement ids are stable and shared by questions of the same requirement.
    rel_qs = [q for q in rubric if q.dimension is Dimension.RELEVANCE]
    assert len({q.requirement_id for q in rel_qs}) == 1


def test_holistic_cap_reduces_relevance_questions():
    gen, _ = _make_generator(_canned_items(), max_questions_per_holistic_dim=3)
    rubric = gen.build("Summarize the article.")

    rel_qs = [q for q in rubric if q.dimension is Dimension.RELEVANCE]
    assert len(rel_qs) == 3, "RELEVANCE must be capped at max_questions_per_holistic_dim"

    # Deterministic: the first three RELEVANCE questions are kept.
    assert [q.text for q in rel_qs] == [
        "Does the answer address aspect 0 of the question?",
        "Does the answer address aspect 1 of the question?",
        "Does the answer address aspect 2 of the question?",
    ]

    # Holistic questions are kept soft, never strict atomic gates (§9).
    assert all(q.must_pass is False for q in rel_qs)

    # Non-holistic questions are untouched by the cap.
    assert any(q.dimension is Dimension.FACTUAL_CONSISTENCY for q in rubric)


def test_temperature_is_not_passed():
    gen, fake = _make_generator(_canned_items())
    gen.build("Summarize the article.")

    # Opus 4.7/4.8 rejects temperature; it must NOT be sent.
    assert "temperature" not in fake.captured
    assert fake.captured["model"] == "claude-opus-4-8"


def test_invalid_enum_values_are_repaired_or_skipped():
    items = [
        # Invalid dimension -> the whole question is skipped.
        {
            "requirement_text": "r",
            "dimension": "not_a_real_dimension",
            "subtype": "unsupported",
            "eval_method": "nli",
            "question_text": "skip me",
            "violation_example": "x",
            "must_pass": False,
        },
        # Invalid subtype/eval_method -> repaired to OTHER / LLM_JUDGE.
        {
            "requirement_text": "r2",
            "dimension": "answer_correctness",
            "subtype": "bogus",
            "eval_method": "bogus",
            "question_text": "keep me",
            "violation_example": "y",
            "must_pass": False,
        },
    ]
    gen, _ = _make_generator(items)
    rubric = gen.build("q")

    assert [q.text for q in rubric] == ["keep me"]
    kept = rubric[0]
    assert kept.dimension is Dimension.ANSWER_CORRECTNESS
    assert kept.subtype is Subtype.OTHER
    assert kept.eval_method is EvalMethod.LLM_JUDGE


def test_handles_markdown_fenced_json():
    fenced = "```json\n" + json.dumps(_canned_items()) + "\n```"
    fake = _FakeAnthropic(fenced)
    gen = ClaudeRubricGenerator(client=fake)

    rubric = gen.build("q")
    assert rubric, "fenced JSON should still parse"
