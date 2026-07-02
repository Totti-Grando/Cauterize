"""Deterministic scorer + primitive checks (spec §6: ``deterministic``).

Exact, free checks: JSON-valid, contains, regex, word count, URL-in-source, etc. The
primitives below are pure functions so they are trivially unit-testable. The scorer reads
an optional ``CHECK:`` directive off ``question.violation_example``; absent one it abstains
with score=1 ("no deterministic check specified").
"""

from __future__ import annotations

import json
import re
from typing import Callable, Optional

from ...contracts import BinaryQuestion, Verdict

# A URL good enough for the deterministic family (full validation is the source_fetch job).
_URL_RE = re.compile(r"https?://[^\s)<>\"']+", re.IGNORECASE)


# -- primitive checks (pure, testable) -------------------------------------------------
def json_valid(text: str) -> bool:
    """True iff ``text`` (stripped) parses as a single JSON value."""
    if text is None:
        return False
    candidate = text.strip()
    if not candidate:
        return False
    try:
        json.loads(candidate)
    except (ValueError, TypeError):
        return False
    return True


def contains(text: str, needle: str) -> bool:
    """True iff ``needle`` occurs in ``text`` (case-insensitive)."""
    return needle.lower() in (text or "").lower()


def not_contains(text: str, needle: str) -> bool:
    """True iff ``needle`` does NOT occur in ``text`` (case-insensitive)."""
    return not contains(text, needle)


def regex_match(text: str, pattern: str) -> bool:
    """True iff ``pattern`` matches anywhere in ``text``. A bad pattern fails closed."""
    try:
        return re.search(pattern, text or "") is not None
    except re.error:
        return False


def max_words(text: str, limit: int) -> bool:
    """True iff ``text`` has at most ``limit`` whitespace-delimited words."""
    return len((text or "").split()) <= int(limit)


def url_present(text: str) -> bool:
    """True iff ``text`` contains at least one http(s) URL."""
    return _URL_RE.search(text or "") is not None


#: Directive name -> a callable ``(response, arg) -> bool``. ``arg`` may be ``None``.
_CHECKS: dict[str, Callable[[str, Optional[str]], bool]] = {
    "json_valid": lambda response, arg: json_valid(response),
    "contains": lambda response, arg: contains(response, arg or ""),
    "not_contains": lambda response, arg: not_contains(response, arg or ""),
    "regex_match": lambda response, arg: regex_match(response, arg or ""),
    "max_words": lambda response, arg: max_words(response, int(arg or 0)),
    "url_present": lambda response, arg: url_present(response),
}

_CHECK_PREFIX = "CHECK:"


def parse_check(directive: str) -> Optional[tuple[str, Optional[str]]]:
    """Parse a ``CHECK:name`` or ``CHECK:name=arg`` directive into ``(name, arg)``.

    Returns ``None`` when ``directive`` carries no ``CHECK:`` prefix.
    """
    if not directive:
        return None
    stripped = directive.strip()
    if not stripped.startswith(_CHECK_PREFIX):
        return None
    body = stripped[len(_CHECK_PREFIX) :].strip()
    if "=" in body:
        name, arg = body.split("=", 1)
        return name.strip(), arg.strip()
    return body, None


class DeterministicScorer:
    """Interprets a ``CHECK:`` directive on ``question.violation_example`` (spec §6).

    The directive names one primitive; the scorer runs it against ``response`` and emits
    score=1 when the check passes (no violation), 0 when it fails. With no directive the
    scorer abstains with score=1 and a clear explanation.
    """

    async def score(
        self, question: BinaryQuestion, response: str, context: str
    ) -> Verdict:
        parsed = parse_check(question.check_directive or question.violation_example)
        if parsed is None:
            return Verdict(
                question_id=question.id,
                score=1,
                explanation="no deterministic check specified",
            )
        name, arg = parsed
        check = _CHECKS.get(name)
        if check is None:
            return Verdict(
                question_id=question.id,
                score=1,
                explanation=f"unknown deterministic check '{name}'; abstaining",
            )
        try:
            passed = check(response or "", arg)
        except (ValueError, TypeError) as exc:
            return Verdict(
                question_id=question.id,
                score=1,
                explanation=f"deterministic check '{name}' could not run ({exc}); abstaining",
            )
        arg_repr = f"={arg}" if arg is not None else ""
        return Verdict(
            question_id=question.id,
            score=1 if passed else 0,
            explanation=(
                f"deterministic check {name}{arg_repr} "
                f"{'passed' if passed else 'failed'}"
            ),
            evidence=f"CHECK:{name}{arg_repr}",
        )
