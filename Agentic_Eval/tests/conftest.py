"""Shared test factories for building rubrics + verdicts cheaply."""

from __future__ import annotations

from aah.contracts import (
    BinaryQuestion,
    Dimension,
    EvalMethod,
    Subtype,
    Verdict,
)


def make_question(
    qid: str,
    dimension: Dimension,
    *,
    subtype: Subtype = Subtype.OTHER,
    eval_method: EvalMethod = EvalMethod.DETERMINISTIC,
    must_pass: bool = False,
) -> BinaryQuestion:
    return BinaryQuestion(
        id=qid,
        requirement_id=f"req-{qid}",
        dimension=dimension,
        subtype=subtype,
        text=f"question {qid}",
        violation_example=f"violation for {qid}",
        eval_method=eval_method,
        must_pass=must_pass,
    )


def make_verdict(qid: str, score: int) -> Verdict:
    return Verdict(question_id=qid, score=score, explanation=f"verdict for {qid}")
