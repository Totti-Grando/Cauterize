"""Layer B — optimization loop (spec §8) on stub modules, plus signal/lesson/guard units."""

from __future__ import annotations

import asyncio

from aah.config import default_weight_config
from aah.contracts import (
    AuditRecord,
    Dimension,
    Lesson,
    LessonKind,
    Mode,
    Verdict,
)
from aah.layer_a.aggregator import aggregate
from aah.layer_b import collect_failures, dedup_and_prune, optimize
from aah.layer_b.notetaker import StubNoteTaker
from aah.layer_b.updater import StubUpdater, enforce_budget
from tests.conftest import make_question, make_verdict


def _record(rubric, verdicts, mode=Mode.QUALITY) -> AuditRecord:
    cfg = default_weight_config()
    scores = aggregate(verdicts, rubric, cfg)
    return AuditRecord(
        mode=mode, task="summarize", question="q", response="resp",
        rubric=rubric, verdicts=verdicts, scores=scores,
        weight_config=cfg, prompt_version="P_Q@v0",
    )


# --- signals ------------------------------------------------------------------

def test_collect_failures_quality_picks_score_zero():
    rubric = [make_question("q1", Dimension.FACTUAL_CONSISTENCY),
              make_question("q2", Dimension.RELEVANCE)]
    rec = _record(rubric, [make_verdict("q1", 0), make_verdict("q2", 1)])
    failures = collect_failures([rec])
    assert [f.question_id for f in failures] == ["q1"]
    assert failures[0].explanation  # the loop's fuel travels with the failure


def test_collect_failures_adversarial_uses_attack_success():
    rubric = [make_question("inj", Dimension.INJECTION_RESISTANCE)]
    v = Verdict(question_id="inj", score=1, explanation="leaked system prompt",
                attack_success=True)
    rec = _record(rubric, [v], mode=Mode.ADVERSARIAL)
    failures = collect_failures([rec])
    assert len(failures) == 1 and failures[0].mode is Mode.ADVERSARIAL


# --- lessons dedup/prune ------------------------------------------------------

def _lesson(lid, text, kind=LessonKind.PROMPTABLE):
    return Lesson(id=lid, source_question_ids=[], explanation_refs=[], text=text,
                  kind=kind, mode=Mode.QUALITY)


def test_dedup_discards_structural_and_merges_duplicates():
    lessons = [
        _lesson("l1", "Bind each statement subject to the right actor"),
        _lesson("l2", "bind each statement subject to the right actor"),  # near-dup
        _lesson("l3", "Provider cannot resist indirect injection", LessonKind.STRUCTURAL),
    ]
    promptable, structural = dedup_and_prune(lessons)
    assert len(promptable) == 1               # near-duplicate merged
    assert len(structural) == 1               # structural routed to findings, not injected


# --- bloat guard --------------------------------------------------------------

def test_enforce_budget_prunes_trailing_lines():
    p_q = "core instruction\n- a\n- b\n- c"
    pruned = enforce_budget(p_q, budget=len("core instruction\n- a"))
    assert pruned.startswith("core instruction")
    assert "- c" not in pruned                # lowest-value (last) lines dropped first


# --- the loop -----------------------------------------------------------------

def test_optimize_converges_after_patch_fixes_the_failure():
    rubric = [make_question("q1", Dimension.FACTUAL_CONSISTENCY)]

    async def run_layer_a(p_q: str, iteration: int):
        # The patched prompt (containing the lesson marker) fixes the failure.
        score = 1 if "BIND-SUBJECT" in p_q else 0
        return [_record(rubric, [make_verdict("q1", score)])]

    result = asyncio.run(
        optimize(
            initial_p_q="You are a faithful summarizer.",
            run_layer_a=run_layer_a,
            notetaker=StubNoteTaker(text="BIND-SUBJECT: tie each claim to its actor."),
            updater=StubUpdater(),
            max_iterations=5,
            budget=2000,
        )
    )

    assert result.converged_reason == "no-new-signal"
    assert "BIND-SUBJECT" in result.best_p_q          # the patch was selected as best
    assert result.best_mean_overall == 1.0
    assert len(result.iterations) == 2                # fail -> patch -> pass


def test_optimize_logs_structural_findings_without_injecting():
    rubric = [make_question("q1", Dimension.INJECTION_RESISTANCE)]

    async def run_layer_a(p_q: str, iteration: int):
        return [_record(rubric, [make_verdict("q1", 0)])]  # never fixed by a prompt

    result = asyncio.run(
        optimize(
            initial_p_q="P_Q",
            run_layer_a=run_layer_a,
            notetaker=StubNoteTaker(text="capability gap", kind=LessonKind.STRUCTURAL),
            updater=StubUpdater(),
            max_iterations=3,
        )
    )
    # Structural lessons are logged as findings and never patched into the prompt.
    assert result.findings and result.converged_reason == "no-promptable-lessons"
    assert result.final_p_q == "P_Q"
