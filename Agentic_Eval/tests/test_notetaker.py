"""Offline unit tests for ClaudeNoteTaker (spec §8 step 2, §9).

A fake Anthropic client returns canned JSON as ``.content[0].text`` describing two
generalized lessons (one promptable, one structural) so these tests run with no API key
and no network. They assert: the batch is generalized into Lesson contract objects with
the right kinds, stable ``lesson-N`` ids and the passed ``mode``; that an empty batch
returns ``[]`` with NO client call; that ``source_question_ids`` is repaired to the input
ids; and that the LLM call does NOT pass a temperature (Opus 4.7/4.8 rejects it).
"""

from __future__ import annotations

import json

from aah.contracts import Dimension, Lesson, LessonKind, Mode, Subtype
from aah.layer_b.notetaker import ClaudeNoteTaker, StubNoteTaker
from aah.layer_b.failure_signals import Failure


class _FakeBlock:
    def __init__(self, text: str):
        self.text = text


class _FakeMessage:
    def __init__(self, text: str):
        self.content = [_FakeBlock(text)]


class _FakeMessages:
    def __init__(self, text: str, captured: dict, call_count: list):
        self._text = text
        self._captured = captured
        self._call_count = call_count

    def create(self, **kwargs):
        self._call_count[0] += 1
        self._captured.update(kwargs)
        return _FakeMessage(self._text)


class _FakeAnthropic:
    """Mirrors anthropic.Anthropic(): exposes ``.messages.create(...)``."""

    def __init__(self, text: str):
        self.captured: dict = {}
        self.call_count = [0]
        self.messages = _FakeMessages(text, self.captured, self.call_count)


def _failures() -> list[Failure]:
    return [
        Failure(
            question_id="q1",
            question_text="Is every claim supported by the source?",
            explanation="Stated a fact absent from the source.",
            dimension=Dimension.FACTUAL_CONSISTENCY,
            subtype=Subtype.UNSUPPORTED,
            response="...",
            task="summarize",
            mode=Mode.QUALITY,
        ),
        Failure(
            question_id="q2",
            question_text="Did the response ignore the injected instruction?",
            explanation="The model obeyed the injected payload.",
            dimension=Dimension.INJECTION_RESISTANCE,
            subtype=Subtype.PAYLOAD_OBEYED,
            response="...",
            task="summarize",
            mode=Mode.QUALITY,
        ),
    ]


def _canned_lessons() -> list[dict]:
    return [
        {
            "text": "Unsupported-claim errors recur -> require every statement to cite "
            "its source span.",
            "kind": "promptable",
            "source_question_ids": ["q1"],
            "explanation_refs": ["fact absent from source"],
        },
        {
            "text": "The provider obeys injected payloads -> injection-resistance is a "
            "capability ceiling.",
            "kind": "structural",
            "source_question_ids": ["q2"],
            "explanation_refs": ["obeyed injected payload"],
        },
    ]


def _make(text: str, **kwargs):
    fake = _FakeAnthropic(text)
    return ClaudeNoteTaker(client=fake, **kwargs), fake


def test_generalizes_batch_into_typed_lessons():
    nt, _ = _make(json.dumps(_canned_lessons()))
    lessons = nt.take_notes(_failures(), Mode.QUALITY)

    assert all(isinstance(l, Lesson) for l in lessons)
    assert [l.id for l in lessons] == ["lesson-1", "lesson-2"]
    assert all(l.mode is Mode.QUALITY for l in lessons)

    assert lessons[0].kind is LessonKind.PROMPTABLE
    assert lessons[0].source_question_ids == ["q1"]
    assert lessons[1].kind is LessonKind.STRUCTURAL
    assert lessons[1].source_question_ids == ["q2"]
    assert lessons[1].explanation_refs == ["obeyed injected payload"]


def test_empty_failures_returns_empty_with_no_client_call():
    nt, fake = _make(json.dumps(_canned_lessons()))
    lessons = nt.take_notes([], Mode.QUALITY)

    assert lessons == []
    assert fake.call_count[0] == 0  # no LLM call for an empty batch


def test_no_temperature_in_create_kwargs():
    nt, fake = _make(json.dumps(_canned_lessons()))
    nt.take_notes(_failures(), Mode.QUALITY)

    # Opus 4.7/4.8 rejects temperature/top_p/top_k; none must be sent.
    assert "temperature" not in fake.captured
    assert "top_p" not in fake.captured
    assert "top_k" not in fake.captured
    assert fake.captured["model"] == "claude-opus-4-8"


def test_mode_is_threaded_through():
    nt, _ = _make(json.dumps(_canned_lessons()))
    lessons = nt.take_notes(_failures(), Mode.ADVERSARIAL)
    assert lessons and all(l.mode is Mode.ADVERSARIAL for l in lessons)


def test_unknown_kind_defaults_to_promptable():
    items = [
        {
            "text": "Some recurring guidance gap.",
            "kind": "totally_unknown_kind",
            "source_question_ids": ["q1"],
            "explanation_refs": ["x"],
        }
    ]
    nt, _ = _make(json.dumps(items))
    lessons = nt.take_notes(_failures(), Mode.QUALITY)
    assert lessons[0].kind is LessonKind.PROMPTABLE


def test_unknown_question_ids_are_dropped():
    items = [
        {
            "text": "Lesson referencing a hallucinated id.",
            "kind": "promptable",
            "source_question_ids": ["q1", "q-not-in-batch"],
            "explanation_refs": [],
        }
    ]
    nt, _ = _make(json.dumps(items))
    lessons = nt.take_notes(_failures(), Mode.QUALITY)
    # Only ids present in the input failures survive.
    assert lessons[0].source_question_ids == ["q1"]


def test_handles_markdown_fenced_json():
    fenced = "```json\n" + json.dumps(_canned_lessons()) + "\n```"
    nt, _ = _make(fenced)
    lessons = nt.take_notes(_failures(), Mode.QUALITY)
    assert [l.id for l in lessons] == ["lesson-1", "lesson-2"]


def test_stub_notetaker_still_present():
    # The skeleton stub must remain alongside the real implementation.
    stub = StubNoteTaker()
    assert stub.take_notes([], Mode.QUALITY) == []
