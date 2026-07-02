"""Rubric-quality loop learning (spec §8 self-update) on stubs."""

from __future__ import annotations

import asyncio

from aah.config import default_weight_config
from aah.contracts import AuditRecord, Dimension, Mode
from aah.layer_a.aggregator import aggregate
from aah.layer_b import critic_collector, defect_objective, optimize
from aah.layer_b.notetaker import StubNoteTaker
from aah.layer_b.rubric_critic import StubRubricCritic
from aah.layer_b.updater import StubUpdater
from tests.conftest import make_question


def _record_with(rubric):
    cfg = default_weight_config()
    return AuditRecord(
        mode=Mode.QUALITY, task="t", question="q", response="",
        rubric=rubric, verdicts=[], scores=aggregate([], rubric, cfg),
        weight_config=cfg, prompt_version="P_R",
    )


def _q(text):
    return make_question("q1", Dimension.RELEVANCE).model_copy(update={"text": text})


def test_stub_critic_flags_matching_items():
    critic = StubRubricCritic(flag_substring="contain PII")
    bad = [_q("Does the response contain PII?")]
    good = [_q("Does the response protect user data?")]
    assert len(asyncio.run(critic.critique(bad, Mode.QUALITY))) == 1
    assert asyncio.run(critic.critique(good, Mode.QUALITY)) == []


def test_learning_loop_patches_guidance_until_critic_is_clean():
    # The driver simulates the rubric generator improving once the guidance carries the fix.
    async def run_layer_a(guidance: str, i: int):
        text = ("Does the response protect user data?"      # good (yes=good)
                if "yes=good" in guidance
                else "Does the response contain PII?")        # bad polarity
        return [_record_with([_q(text)])]

    result = asyncio.run(
        optimize(
            initial_p_q="",  # empty rubric guidance
            run_layer_a=run_layer_a,
            notetaker=StubNoteTaker(text="Phrase every check as yes=good."),
            updater=StubUpdater(),
            mode=Mode.QUALITY,
            collect=critic_collector(StubRubricCritic(flag_substring="contain PII")),
            objective_fn=defect_objective,
            max_iterations=5,
        )
    )
    assert result.converged_reason == "no-new-signal"   # critic satisfied
    assert "yes=good" in result.best_p_q                 # the learned guidance was selected
    assert len(result.iterations) == 2                   # defect -> patch -> clean


def test_no_defects_converges_immediately():
    async def run_layer_a(guidance: str, i: int):
        return [_record_with([_q("Does the response stay on topic?")])]

    result = asyncio.run(
        optimize(
            initial_p_q="",
            run_layer_a=run_layer_a,
            notetaker=StubNoteTaker(),
            updater=StubUpdater(),
            mode=Mode.QUALITY,
            collect=critic_collector(StubRubricCritic()),  # flags nothing
            objective_fn=defect_objective,
            max_iterations=5,
        )
    )
    assert result.converged_reason == "no-new-signal"
    assert result.best_iteration == 0
