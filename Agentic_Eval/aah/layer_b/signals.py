"""Failure-signal collection (spec §8 step 1). Layer B reads Layer A's AuditRecords.

The loop consumes the *pairing* of each failed verdict with its ``explanation`` — a bare 0
is not enough to learn from (§8). In quality mode a failure is a score-0 verdict; in
adversarial mode it is ``attack_success == true``. Each Failure carries the explanation and
the {dimension, subtype} tags (§6), which are exactly the NoteTaker's inputs.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from ..contracts import AuditRecord, BinaryQuestion, Dimension, Mode, Subtype


class Failure(BaseModel):
    """One failed verdict, joined with its question context. The fuel for the loop (§8)."""

    model_config = ConfigDict(frozen=True)

    question_id: str
    question_text: str
    explanation: str
    dimension: Dimension
    subtype: Subtype
    response: str
    task: str
    mode: Mode


def _is_failure(verdict, mode: Mode) -> bool:
    if mode is Mode.ADVERSARIAL:
        return bool(verdict.attack_success)
    # quality / hybrid: a score-0 verdict is the failure signal
    return verdict.score == 0


def collect_failures(records: list[AuditRecord]) -> list[Failure]:
    """Pull failed verdicts (with explanation + {dimension, subtype}) from AuditRecords."""

    failures: list[Failure] = []
    for rec in records:
        q_by_id: dict[str, BinaryQuestion] = {q.id: q for q in rec.rubric}
        for v in rec.verdicts:
            if not _is_failure(v, rec.mode):
                continue
            q = q_by_id.get(v.question_id)
            if q is None:
                continue
            failures.append(
                Failure(
                    question_id=v.question_id,
                    question_text=q.text,
                    explanation=v.explanation,
                    dimension=q.dimension,
                    subtype=q.subtype,
                    response=rec.response,
                    task=rec.task,
                    mode=rec.mode,
                )
            )
    return failures
