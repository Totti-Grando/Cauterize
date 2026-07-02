"""EvaluatorRouter interface (spec §5 step 5, §6). [M1 owner: A4]

Routes each BinaryQuestion by ``eval_method`` to the cheapest competent scorer and returns
a Verdict {score, explanation, evidence}. The stub routes everything to a fixed-verdict
scorer so the skeleton runs; M1 wires deterministic / nli / source_fetch / llm_judge.
"""

from __future__ import annotations

from typing import Any, Optional, Protocol

from ..contracts import BinaryQuestion, EvalMethod, Verdict
from .scorers import (
    ClaudeJudgeScorer,
    ClaudeNLIScorer,
    DeterministicScorer,
    FabricationScorer,
    InjectionDetectorScorer,
    Scorer,
    SourceFetchScorer,
)


class EvaluatorRouter(Protocol):
    async def score(self, question: BinaryQuestion, response: str, context: str) -> Verdict: ...


class StubEvaluatorRouter:
    """Skeleton stub: emits a constant score with a placeholder explanation. Replaced in M1."""

    def __init__(self, score: int = 1):
        self._score = score

    async def score(self, question: BinaryQuestion, response: str, context: str) -> Verdict:
        return Verdict(
            question_id=question.id,
            score=self._score,
            explanation="stub router: constant verdict",
        )


class RealEvaluatorRouter:
    """Routes each question by ``eval_method`` to the cheapest competent scorer (§6).

    Construct with a ``{EvalMethod: Scorer}`` mapping (use :func:`default_router` to wire
    the five concrete scorers). An unmapped ``eval_method`` raises a clear error rather than
    silently scoring.
    """

    def __init__(self, scorers: dict[EvalMethod, Scorer]):
        self._scorers: dict[EvalMethod, Scorer] = dict(scorers)

    async def score(self, question: BinaryQuestion, response: str, context: str) -> Verdict:
        scorer = self._scorers.get(question.eval_method)
        if scorer is None:
            raise KeyError(
                f"no scorer registered for eval_method {question.eval_method!r} "
                f"(question {question.id!r})"
            )
        return await scorer.score(question, response, context)


def default_router(
    client: Any = None,
    fetcher: Optional[Any] = None,
    model: str = "claude-opus-4-8",
) -> RealEvaluatorRouter:
    """Wire the five scorers into a :class:`RealEvaluatorRouter`.

    ``client`` (an Anthropic async client) and ``fetcher`` (a ``url -> text`` callable) are
    injectable so the whole router runs offline in tests; left as ``None`` they are built
    lazily at runtime. The NLI scorer is shared with the source-fetch scorer's claim-check.
    """
    nli = ClaudeNLIScorer(client=client, model=model)
    scorers: dict[EvalMethod, Scorer] = {
        EvalMethod.DETERMINISTIC: DeterministicScorer(),
        EvalMethod.NLI: nli,
        EvalMethod.INJECTION_DETECTOR: InjectionDetectorScorer(),
        EvalMethod.SOURCE_FETCH: SourceFetchScorer(
            nli=nli, fetcher=fetcher, client=client, model=model
        ),
        EvalMethod.SOURCE_CHECK: FabricationScorer(),  # F3: deterministic fabrication gate
        EvalMethod.LLM_JUDGE: ClaudeJudgeScorer(client=client, model=model),
    }
    return RealEvaluatorRouter(scorers)
