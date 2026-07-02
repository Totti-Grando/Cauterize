"""Updater interface (spec §8 step 4) + the prompt-length bloat guard (§9).

Locates the substring of P_Q a lesson bears on and rewrites it in place. Critically, it
enforces a prompt-length budget: if a patch would exceed it, prune the lowest-value existing
instruction instead of appending (a meta-prompt that grew 22 -> 6,248 chars collapsed across
all categories — past a critical length, instructions hurt regardless of correctness, §9).

The stub appends lessons under budget so the Orchestrator is testable without an LLM. The
real ClaudeUpdater (substring locate + rewrite) is built by a subagent against this interface.
"""

from __future__ import annotations

import json
import os
from typing import Any, Protocol

from ..contracts import Lesson


class Updater(Protocol):
    def patch(self, p_q: str, lessons: list[Lesson], *, budget: int) -> str: ...


def enforce_budget(p_q: str, budget: int) -> str:
    """Prune trailing instruction lines until P_Q fits ``budget`` chars (the §9 bloat guard).

    Lines are the instruction unit; the last (lowest-value, most-recently-appended) lines are
    dropped first. Shared so both the stub and the real updater apply the same guard.
    """

    if len(p_q) <= budget:
        return p_q
    lines = p_q.splitlines()
    if not lines:
        return p_q
    # Drop the lowest-value (last) instruction lines first, but NEVER below the first line —
    # collapsing P_Q to '' would silently invalidate every downstream evaluation (audit #3).
    while len(lines) > 1 and len("\n".join(lines)) > budget:
        lines.pop()
    result = "\n".join(lines)
    if len(result) > budget:
        # The core (first) instruction alone exceeds the budget: truncate it rather than
        # returning an empty prompt.
        result = result[:budget]
    return result


class StubUpdater:
    """Skeleton stub: append each lesson as a bullet, then apply the budget guard."""

    def patch(self, p_q: str, lessons: list[Lesson], *, budget: int) -> str:
        if not lessons:
            return p_q
        additions = "\n".join(f"- {lesson.text}" for lesson in lessons)
        candidate = f"{p_q}\n{additions}" if p_q else additions
        return enforce_budget(candidate, budget)


_EDIT_SCHEMA_NOTE = (
    'Return a JSON object with one key "edits": a list of {"old": str, "new": str} '
    'pairs. Each "old" MUST be an EXACT substring already present in P_Q to be rewritten '
    'in place to "new" (the locate-substring-then-replace mechanic). If a lesson has no '
    'anchoring substring in P_Q, return an empty string for "old" and put the full new '
    'instruction line in "new" so it can be appended. Make MINIMAL edits.'
)


class ClaudeUpdater:
    """Real Updater: ask Claude for minimal substring edits to P_Q (spec §8 step 4).

    For the batch of promptable lessons, a single LLM call returns a structured list of
    ``{old, new}`` pairs. Each ``old`` is located as an existing substring of P_Q and
    rewritten to ``new`` via one ``str.replace`` (skip when ``old`` is absent). Lessons
    with no anchoring substring may be appended as new instruction lines. The §9 bloat
    guard (``enforce_budget``) then prunes trailing instructions past ``budget`` rather
    than letting the prompt grow unboundedly — "prune, don't append".
    """

    def __init__(self, client: Any = None, model: str = "claude-opus-4-8") -> None:
        self._client = client
        self.model = model

    def _ensure_client(self) -> Any:
        if self._client is None:
            import anthropic  # lazy import so unit tests stay offline

            self._client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
        return self._client

    def _request_edits(self, p_q: str, lessons: list[Lesson]) -> list[dict]:
        client = self._ensure_client()
        lessons_block = "\n".join(f"- (lesson {ls.id}) {ls.text}" for ls in lessons)
        prompt = (
            f"{_EDIT_SCHEMA_NOTE}\n\n"
            f"=== CURRENT P_Q ===\n{p_q}\n=== END P_Q ===\n\n"
            f"=== LESSONS TO APPLY ===\n{lessons_block}\n=== END LESSONS ===\n\n"
            "Output ONLY the JSON object."
        )
        # NOTE: claude-opus-4-8 rejects temperature/top_p/top_k (HTTP 400) — do not send them.
        response = client.messages.create(
            model=self.model,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
        text = self._extract_text(response)
        return self._parse_edits(text)

    @staticmethod
    def _extract_text(response: Any) -> str:
        parts: list[str] = []
        for block in getattr(response, "content", None) or []:
            if getattr(block, "type", None) == "text" or hasattr(block, "text"):
                parts.append(getattr(block, "text", "") or "")
        return "".join(parts)

    @staticmethod
    def _parse_edits(text: str) -> list[dict]:
        text = (text or "").strip()
        if not text:
            return []
        # Tolerate prose/code fences around the JSON by slicing to the outermost braces.
        start = text.find("{")
        bracket = text.find("[")
        if bracket != -1 and (start == -1 or bracket < start):
            start, end = bracket, text.rfind("]")
        else:
            end = text.rfind("}")
        if start == -1 or end == -1 or end < start:
            return []
        try:
            data = json.loads(text[start : end + 1])
        except (ValueError, TypeError):
            return []
        if isinstance(data, dict):
            data = data.get("edits", [])
        if not isinstance(data, list):
            return []
        return [e for e in data if isinstance(e, dict)]

    def patch(self, p_q: str, lessons: list[Lesson], *, budget: int) -> str:
        if not lessons:
            return p_q  # no LLM call for an empty batch

        edits = self._request_edits(p_q, lessons)

        result = p_q
        appends: list[str] = []
        for edit in edits:
            old = edit.get("old") or ""
            new = edit.get("new") or ""
            if old:
                # locate substring s_k, rewrite to s'_k, replace(s_k, s'_k) — only if present
                if old in result:
                    result = result.replace(old, new)
                # skip edits whose anchor is not found (no crash, no change)
            elif new:
                appends.append(new)  # no anchor → candidate new instruction line

        if appends:
            additions = "\n".join(appends)
            result = f"{result}\n{additions}" if result else additions

        # §9 bloat guard: prune lowest-value trailing instructions past the budget.
        return enforce_budget(result, budget)
