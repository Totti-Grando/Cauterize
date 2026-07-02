"""F7: verbosity & position guards — judge doesn't reward length; padding doesn't help."""

from __future__ import annotations

import asyncio

from aah.contracts import Dimension, EvalMethod
from aah.layer_a.scorers import DeterministicScorer
from aah.layer_a.scorers.llm_judge import _SYSTEM as JUDGE_SYSTEM
from tests.conftest import make_question


def test_judge_prompt_has_verbosity_and_position_guards():
    low = JUDGE_SYSTEM.lower()
    assert "do not reward length" in low
    assert "padding" in low
    assert "canonical order" in low and "position carries no meaning" in low


def test_padded_answer_scores_no_higher_than_concise_under_length_check():
    # A relevance/completeness check that caps length: a padded, empty answer fails it while a
    # concise correct one passes — padding never scores higher.
    q = make_question("r", Dimension.RELEVANCE, eval_method=EvalMethod.DETERMINISTIC).model_copy(
        update={"check_directive": "CHECK:max_words=8"})
    concise = asyncio.run(DeterministicScorer().score(q, "Net sentiment declined this quarter.", ""))
    padded = asyncio.run(DeterministicScorer().score(
        q, "Well, to be perfectly honest and thorough here, it must be said that " * 3, ""))
    assert concise.score == 1
    assert padded.score == 0
    assert padded.score <= concise.score
