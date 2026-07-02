"""Lesson dedup + prune (spec §8 step 3).

Merge near-identical lessons so the injected set stays unique, and split off ``structural``
lessons: those are provider *capability* findings (often injection-resistance) and must be
logged, never injected into P_Q (§8, §9). Promptable lessons are deduped by normalized text
plus a token-overlap (Jaccard) near-duplicate check.
"""

from __future__ import annotations

import re

from ..contracts import Lesson, LessonKind


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 2}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def dedup_and_prune(
    lessons: list[Lesson], *, jaccard_threshold: float = 0.8
) -> tuple[list[Lesson], list[Lesson]]:
    """Return ``(promptable_unique, structural_findings)``.

    Structural lessons are routed to findings (logged, not injected). Promptable lessons are
    kept in first-seen order, dropping any that are an exact normalized duplicate of, or a
    near-duplicate (Jaccard over ``jaccard_threshold``) with, a lesson already kept.
    """

    structural: list[Lesson] = []
    promptable_unique: list[Lesson] = []
    seen_norm: set[str] = set()
    seen_tokens: list[set[str]] = []

    for lesson in lessons:
        if lesson.kind is LessonKind.STRUCTURAL:
            structural.append(lesson)
            continue
        norm = _normalize(lesson.text)
        if norm in seen_norm:
            continue
        toks = _tokens(lesson.text)
        if any(_jaccard(toks, prev) >= jaccard_threshold for prev in seen_tokens):
            continue
        seen_norm.add(norm)
        seen_tokens.append(toks)
        promptable_unique.append(lesson)

    return promptable_unique, structural
