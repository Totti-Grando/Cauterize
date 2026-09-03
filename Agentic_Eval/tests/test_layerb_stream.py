"""Layer B in the loop: objective (learning/attack), lessons events, escalation, rubric breakdown."""

from __future__ import annotations

from aah.api import live_engine as engine, offline_fixtures as scenario
from aah.api.ui_adapter import audit_to_evaluation
from aah.api.config_store import ConfigStore
from aah.contracts import Mode


def _store():
    return ConfigStore()  # no creds → deterministic offline path


async def _collect(gen):
    return [e async for e in gen]


# --- objective wiring -----------------------------------------------------------------
def test_plan_manual_attack_is_adversarial_and_escalates():
    plan = engine.plan_manual(_store(), "ravenpack", "summarize the risk", None,
                              objective="attack", lessons=[])
    assert plan.mode is Mode.ADVERSARIAL and plan.objective == "attack"
    job = plan.jobs[0]
    assert job.meta.get("original") == "summarize the risk"
    assert job.question and job.question != "summarize the risk"  # escalated probe


def test_plan_manual_learning_is_quality_and_verbatim():
    plan = engine.plan_manual(_store(), "ravenpack", "summarize the risk", None,
                              objective="learning", lessons=[])
    assert plan.mode is Mode.QUALITY and plan.objective == "learning"
    assert plan.jobs[0].question == "summarize the risk"  # sent as-is


def test_guidance_excludes_structural_and_escalate_uses_lessons():
    g = engine._guidance_from([{"text": "attribute claims", "kind": "promptable"},
                               {"text": "leak ceiling", "kind": "structural"}])
    assert "attribute claims" in g and "leak ceiling" not in g  # only promptable → guidance
    esc = engine._escalate("base probe", [{"text": "prior leak trick"}], live=False)
    assert "base probe" in esc and "prior leak trick" in esc and esc != "base probe"


# --- streaming: lessons + escalation + rubric -----------------------------------------
async def test_manual_attack_emits_escalation_and_lessons():
    plan = engine.plan_manual(_store(), "ravenpack", "summarize the risk", None,
                              objective="attack", lessons=[])
    evs = await _collect(engine.stream_eval(plan))
    types = [e["type"] for e in evs]
    assert "escalated_question" in types
    assert "lessons" in types  # the landed attack produces a (structural) lesson
    lessons_ev = next(e for e in evs if e["type"] == "lessons")
    assert lessons_ev["structural"]  # attack landing is a structural finding


async def test_auto_loop_streams_rounds_and_done():
    evs = await _collect(engine.stream_run_loop(_store(), "ravenpack", "learning", 3))
    assert evs[-1]["type"] == "done"
    assert any(e["type"] == "evaluation" for e in evs)


async def test_auto_attack_loop_converges():
    evs = await _collect(engine.stream_run_loop(_store(), "ravenpack", "attack", 5))
    # the offline attack yields the same structural lesson each round → converges before 5.
    assert any(e["type"] == "log" and e.get("step") == "Converged" for e in evs)


# --- adapter rubric breakdown ---------------------------------------------------------
async def test_adapter_includes_rubric_breakdown_and_tiers():
    case = scenario.CASES[0]
    rec = await scenario.run_case(case)
    ev = audit_to_evaluation(rec, scenario.case_meta(case, "RavenPack"))
    assert ev["rubric"] and all("checks" in g for g in ev["rubric"])
    check = ev["rubric"][0]["checks"][0]
    assert {"tier", "score", "dimension", "eval_method"} <= set(check)
    assert isinstance(ev["perDimension"], list)
    assert "gatedBy" in ev
