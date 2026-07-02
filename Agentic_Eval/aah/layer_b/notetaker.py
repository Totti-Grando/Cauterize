"""NoteTaker interface (spec §8 step 2). [M3 owner: real impl built by a subagent]

Feeds a *batch* of (question + explanation + {dimension, subtype}) to a note-taker that
generalizes them into Lessons (e.g. "attribution errors recur -> bind each statement's
subject to the right actor"), each classified ``promptable`` vs ``structural`` (§8, §9).
The stub returns one canned promptable lesson so the Orchestrator is testable without an LLM.
"""

from __future__ import annotations

import json
import re
from typing import Any, Protocol

from ..contracts import Lesson, LessonKind, Mode
from .signals import Failure


class NoteTaker(Protocol):
    def take_notes(self, failures: list[Failure], mode: Mode) -> list[Lesson]: ...


class StubNoteTaker:
    """Skeleton stub: one promptable lesson summarizing the batch. Replaced by ClaudeNoteTaker."""

    def __init__(self, text: str = "Address the recurring failure.", kind: LessonKind = LessonKind.PROMPTABLE):
        self._text = text
        self._kind = kind

    def take_notes(self, failures: list[Failure], mode: Mode) -> list[Lesson]:
        if not failures:
            return []
        return [
            Lesson(
                id="lesson-stub-1",
                source_question_ids=[f.question_id for f in failures],
                explanation_refs=[f.explanation for f in failures],
                text=self._text,
                kind=self._kind,
                mode=mode,
            )
        ]


class ClaudeNoteTaker:
    """Claude-backed NoteTaker (spec §8 step 2, §9).

    Feeds the *whole batch* of failures -- each carrying ``question_text``,
    ``explanation``, ``dimension`` and ``subtype`` -- to Claude in a single call and asks
    it to GENERALIZE recurring failures into a small set of :class:`Lesson` objects (e.g.
    "attribution errors recur -> bind each statement's subject to the right actor").

    Each lesson is classified ``promptable`` vs ``structural`` (§8, §9):

    * ``promptable`` -- a guidance gap fixable by editing the question-generation prompt
      ``P_Q``. These patch the prompt downstream.
    * ``structural`` -- a provider capability limit (often injection-resistance) that
      prompt-tuning cannot fix. These are logged as provider findings, not injected.

    The Anthropic client is injectable for offline unit testing; at runtime it is lazily
    built from ``ANTHROPIC_API_KEY``. The Opus 4.7/4.8 family does not accept a temperature
    parameter, so none is sent (it would 400).
    """

    def __init__(self, client: Any = None, model: str = "claude-opus-4-8"):
        self._client = client
        self._model = model

    # -- client ----------------------------------------------------------------
    def _get_client(self) -> Any:
        """Lazily build an ``anthropic.Anthropic()`` client on first use."""
        if self._client is None:
            import anthropic

            self._client = anthropic.Anthropic()
        return self._client

    # -- public API ------------------------------------------------------------
    def take_notes(self, failures: list[Failure], mode: Mode) -> list[Lesson]:
        if not failures:
            return []  # no LLM call for an empty batch

        client = self._get_client()
        prompt = self._build_prompt(failures, mode)
        response = client.messages.create(
            model=self._model,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        text = self._extract_text(response)
        raw_items = self._parse_json(text)
        valid_ids = {f.question_id for f in failures}
        return self._to_lessons(raw_items, valid_ids, mode)

    # -- prompt ----------------------------------------------------------------
    @staticmethod
    def _build_prompt(failures: list[Failure], mode: Mode) -> str:
        lines: list[str] = []
        for f in failures:
            lines.append(
                json.dumps(
                    {
                        "question_id": f.question_id,
                        "dimension": f.dimension.value,
                        "subtype": f.subtype.value,
                        "question_text": f.question_text,
                        "explanation": f.explanation,
                    }
                )
            )
        batch = "\n".join(lines)
        return (
            "You are the NoteTaker in an agent-evaluation loop. You are given a BATCH of "
            f"individual evaluation FAILURES from a single {mode.value}-mode run. Each "
            "failure is a JSON object with a question_id, its {dimension, subtype} tags, "
            "the evaluation question_text, and the explanation of why it failed.\n\n"
            "Your job is to GENERALIZE the recurring failures into a SMALL set of distinct "
            "Lessons (merge failures that share a root cause; do not emit one lesson per "
            "failure). Each lesson is a single actionable instruction, e.g. 'attribution "
            "errors recur -> bind each statement's subject to the right actor'.\n\n"
            "Classify each lesson:\n"
            "- \"promptable\": a guidance gap fixable by editing the question-generation "
            "prompt (the instructions given to the system under test). Most factual, "
            "formatting, completeness, relevance and instruction-following gaps are "
            "promptable.\n"
            "- \"structural\": a provider capability limit that prompt-tuning CANNOT fix -- "
            "typically injection-resistance and other security/data-leakage ceilings. "
            "These are provider findings, not prompt fixes.\n\n"
            "Return ONLY a JSON array (no prose, no markdown fences). Each element is an "
            "object with exactly these fields:\n"
            "{\n"
            '  "text": str,                      // the generalized lesson\n'
            '  "kind": "promptable" | "structural",\n'
            '  "source_question_ids": [str],     // subset of the input question_ids this '
            "lesson generalizes\n"
            '  "explanation_refs": [str]         // short references back to the failing '
            "explanations\n"
            "}\n\n"
            f"FAILURES (one JSON object per line):\n{batch}"
        )

    # -- response parsing ------------------------------------------------------
    @staticmethod
    def _extract_text(response: Any) -> str:
        """Pull the text out of an Anthropic Messages response (or a fake/dict block)."""
        content = getattr(response, "content", None)
        if content is None:
            return ""
        parts: list[str] = []
        for block in content:
            text = getattr(block, "text", None)
            if text is None and isinstance(block, dict):
                text = block.get("text")
            if text:
                parts.append(text)
        return "".join(parts)

    @staticmethod
    def _parse_json(text: str) -> list[dict[str, Any]]:
        """Parse the model's JSON array, tolerating markdown fences / surrounding prose."""
        if not text or not text.strip():
            return []
        candidate = text.strip()
        fence = re.search(r"```(?:json)?\s*(.*?)```", candidate, re.DOTALL)
        if fence:
            candidate = fence.group(1).strip()
        try:
            data = json.loads(candidate)
        except (ValueError, TypeError):
            start = candidate.find("[")
            end = candidate.rfind("]")
            if start == -1 or end == -1 or end <= start:
                return []
            try:
                data = json.loads(candidate[start : end + 1])
            except (ValueError, TypeError):
                return []
        if isinstance(data, dict):
            for key in ("lessons", "items"):
                if isinstance(data.get(key), list):
                    data = data[key]
                    break
            else:
                data = [data]
        if not isinstance(data, list):
            return []
        return [item for item in data if isinstance(item, dict)]

    @staticmethod
    def _coerce_kind(value: Any) -> LessonKind:
        """Map a string onto a :class:`LessonKind`; unknown -> PROMPTABLE (§8 default)."""
        if isinstance(value, LessonKind):
            return value
        if isinstance(value, str):
            key = value.strip().lower().replace(" ", "_").replace("-", "_")
            for member in LessonKind:
                if member.value == key or member.name.lower() == key:
                    return member
        return LessonKind.PROMPTABLE

    @staticmethod
    def _coerce_str_list(value: Any) -> list[str]:
        """Coerce a value into a list of non-empty strings."""
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, (list, tuple)):
            return []
        out: list[str] = []
        for item in value:
            if item is None:
                continue
            s = str(item).strip()
            if s:
                out.append(s)
        return out

    def _to_lessons(
        self,
        items: list[dict[str, Any]],
        valid_ids: set[str],
        mode: Mode,
    ) -> list[Lesson]:
        lessons: list[Lesson] = []
        index = 0
        for item in items:
            text = str(item.get("text") or "").strip()
            if not text:
                continue  # a lesson with no instruction is useless -> skip
            kind = self._coerce_kind(item.get("kind"))
            # source_question_ids must only reference ids present in the input batch.
            source_ids = [
                qid
                for qid in self._coerce_str_list(item.get("source_question_ids"))
                if qid in valid_ids
            ]
            explanation_refs = self._coerce_str_list(item.get("explanation_refs"))
            index += 1
            lessons.append(
                Lesson(
                    id=f"lesson-{index}",
                    source_question_ids=source_ids,
                    explanation_refs=explanation_refs,
                    text=text,
                    kind=kind,
                    mode=mode,
                )
            )
        return lessons
