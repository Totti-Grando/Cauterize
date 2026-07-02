"""Offline unit tests for the real Claude-backed ClaudeUpdater (spec §8 step 4, §9).

A fake Anthropic client injects canned JSON edits so the whole suite runs without a
network call or an API key. The fake records every ``messages.create`` kwarg so we can
assert the repo constraint that ``temperature`` is never sent (claude-opus-4-8 400s on it).
"""

from __future__ import annotations

import json

from aah.contracts import Lesson, LessonKind, Mode
from aah.layer_b.updater import ClaudeUpdater, enforce_budget


# --- fakes --------------------------------------------------------------------

class _Block:
    def __init__(self, text: str) -> None:
        self.type = "text"
        self.text = text


class _Response:
    def __init__(self, text: str) -> None:
        self.content = [_Block(text)]


class FakeClient:
    """Stand-in for anthropic.Anthropic; returns canned edits as .content[0].text."""

    def __init__(self, edits) -> None:
        # Accept a ready JSON string or a python object to serialize.
        self._payload = edits if isinstance(edits, str) else json.dumps(edits)
        self.calls: list[dict] = []
        self.messages = self  # so client.messages.create(...) lands here

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return _Response(self._payload)


def _lesson(lid: str, text: str, kind: LessonKind = LessonKind.PROMPTABLE) -> Lesson:
    return Lesson(id=lid, source_question_ids=[], explanation_refs=[], text=text,
                  kind=kind, mode=Mode.QUALITY)


# --- substring rewrite --------------------------------------------------------

def test_patch_applies_substring_rewrite():
    p_q = "You are a faithful summarizer."
    fake = FakeClient({"edits": [
        {"old": "faithful summarizer",
         "new": "faithful summarizer who binds each claim to its actor"},
    ]})
    updater = ClaudeUpdater(client=fake)

    out = updater.patch(p_q, [_lesson("l1", "bind claims to actors")], budget=2000)

    assert out == "You are a faithful summarizer who binds each claim to its actor."
    assert len(fake.calls) == 1  # exactly one LLM call for the batch


def test_edit_with_missing_old_is_skipped():
    p_q = "You are a faithful summarizer."
    fake = FakeClient({"edits": [
        {"old": "this text is NOT in P_Q", "new": "should never appear"},
        {"old": "faithful", "new": "scrupulously faithful"},
    ]})
    updater = ClaudeUpdater(client=fake)

    out = updater.patch(p_q, [_lesson("l1", "x")], budget=2000)

    assert "should never appear" not in out      # unanchored edit had no effect
    assert out == "You are a scrupulously faithful summarizer."  # the found edit applied


def test_lesson_without_anchor_is_appended_as_new_line():
    p_q = "Core instruction."
    fake = FakeClient({"edits": [
        {"old": "", "new": "- Always cite the source sentence for each claim."},
    ]})
    updater = ClaudeUpdater(client=fake)

    out = updater.patch(p_q, [_lesson("l1", "cite sources")], budget=2000)

    assert out == "Core instruction.\n- Always cite the source sentence for each claim."


# --- budget guard (§9) --------------------------------------------------------

def test_budget_guard_prunes_trailing_lines():
    p_q = "core instruction"
    # Three unanchored lessons append three trailing instruction lines.
    fake = FakeClient({"edits": [
        {"old": "", "new": "- aaaaaaaaaa"},
        {"old": "", "new": "- bbbbbbbbbb"},
        {"old": "", "new": "- cccccccccc"},
    ]})
    updater = ClaudeUpdater(client=fake)

    tiny = len("core instruction\n- aaaaaaaaaa")
    out = updater.patch(p_q, [_lesson("l1", "x")], budget=tiny)

    assert len(out) <= tiny                       # fits the budget
    assert out.startswith("core instruction")
    assert "- cccccccccc" not in out              # lowest-value trailing line pruned
    # Same semantics as the shared helper.
    full = "core instruction\n- aaaaaaaaaa\n- bbbbbbbbbb\n- cccccccccc"
    assert out == enforce_budget(full, tiny)


# --- empty batch --------------------------------------------------------------

def test_empty_lessons_returns_p_q_unchanged_without_calling_client():
    p_q = "Untouched prompt."
    fake = FakeClient({"edits": []})
    updater = ClaudeUpdater(client=fake)

    out = updater.patch(p_q, [], budget=2000)

    assert out == p_q
    assert fake.calls == []                       # no LLM call on an empty batch


# --- repo constraint: no temperature -----------------------------------------

def test_create_kwargs_never_include_temperature():
    fake = FakeClient({"edits": [{"old": "a", "new": "b"}]})
    updater = ClaudeUpdater(client=fake)

    updater.patch("a sentence", [_lesson("l1", "x")], budget=2000)

    assert fake.calls, "expected one recorded create() call"
    kwargs = fake.calls[0]
    assert "temperature" not in kwargs
    assert "top_p" not in kwargs
    assert "top_k" not in kwargs
    assert kwargs["model"] == "claude-opus-4-8"
