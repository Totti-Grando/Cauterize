"""Rubric normalization routes checks to a scorer that grades the response (spec fix)."""

from __future__ import annotations

from aah.contracts import Dimension, EvalMethod, Mode
from aah.layer_a.rubric_norm import guard_security_gates, normalize_rubric, prepare_rubric
from tests.conftest import make_question


def _q(qid, dimension, eval_method, violation_example):
    return make_question(qid, dimension, eval_method=eval_method).model_copy(
        update={"violation_example": violation_example}
    )


def test_deterministic_without_check_becomes_judge():
    q = _q("d", Dimension.ANSWER_CORRECTNESS, EvalMethod.DETERMINISTIC, "some prose, no directive")
    (out,) = normalize_rubric([q])
    assert out.eval_method is EvalMethod.LLM_JUDGE


def test_deterministic_with_check_is_kept():
    q = _q("d", Dimension.ANSWER_CORRECTNESS, EvalMethod.DETERMINISTIC, "CHECK:contains=Paris")
    (out,) = normalize_rubric([q])
    assert out.eval_method is EvalMethod.DETERMINISTIC


def test_check_directive_field_survives_when_violation_example_is_prose():
    """Audit finding #1: an LLM-generated check carries a prose violation_example AND a machine
    check_directive; normalization must honor the directive, not collapse to a judge."""
    q = make_question("d", Dimension.ANSWER_CORRECTNESS, eval_method=EvalMethod.DETERMINISTIC).model_copy(
        update={"violation_example": "Returns prose instead of JSON.", "check_directive": "CHECK:json_valid"}
    )
    (out,) = normalize_rubric([q])
    assert out.eval_method is EvalMethod.DETERMINISTIC


def test_injection_check_directive_survives_with_prose_example():
    q = make_question("a", Dimension.DATA_LEAKAGE, eval_method=EvalMethod.INJECTION_DETECTOR).model_copy(
        update={"violation_example": "The system prompt leaks.", "check_directive": "ATTACK:canary=X"}
    )
    (out,) = normalize_rubric([q])
    assert out.eval_method is EvalMethod.INJECTION_DETECTOR


def test_holistic_nli_becomes_judge():
    q = _q("r", Dimension.RELEVANCE, EvalMethod.NLI, "off-topic answer")
    (out,) = normalize_rubric([q])
    assert out.eval_method is EvalMethod.LLM_JUDGE


def test_injection_with_attack_is_kept():
    q = _q("a", Dimension.DATA_LEAKAGE, EvalMethod.INJECTION_DETECTOR, "ATTACK:canary=X")
    (out,) = normalize_rubric([q])
    assert out.eval_method is EvalMethod.INJECTION_DETECTOR


# --- security-gate guard ------------------------------------------------------

def test_guard_reclassifies_misfiled_security_check_in_quality_mode():
    # A helpfulness check mis-tagged as unsafe_tool_use (CRITICAL) + must_pass.
    q = make_question("m", Dimension.UNSAFE_TOOL_USE, eval_method=EvalMethod.LLM_JUDGE,
                      must_pass=True)
    (out,) = guard_security_gates([q], Mode.QUALITY)
    assert out.dimension is Dimension.ANSWER_CORRECTNESS   # moved out of the security gate
    assert out.must_pass is False                          # and can no longer gate


def test_guard_strips_must_pass_from_judge_checks_in_quality_mode():
    q = make_question("j", Dimension.FACTUAL_CONSISTENCY, eval_method=EvalMethod.LLM_JUDGE,
                      must_pass=True)
    (out,) = guard_security_gates([q], Mode.QUALITY)
    assert out.must_pass is False                          # a judge check can't hard-gate quality


def test_guard_keeps_must_pass_on_deterministic_check():
    q = _q("d", Dimension.INSTRUCTION_FOLLOWING, EvalMethod.DETERMINISTIC, "CHECK:json_valid")
    q = q.model_copy(update={"must_pass": True})
    (out,) = guard_security_gates([q], Mode.QUALITY)
    assert out.must_pass is True                           # concrete rule may still gate


def test_guard_keeps_real_security_probe():
    q = make_question("p", Dimension.DATA_LEAKAGE, eval_method=EvalMethod.INJECTION_DETECTOR,
                      must_pass=True)
    (out,) = guard_security_gates([q], Mode.QUALITY)
    assert out.dimension is Dimension.DATA_LEAKAGE         # a genuine probe stays gating


def test_guard_is_a_noop_in_adversarial_mode():
    q = make_question("m", Dimension.UNSAFE_TOOL_USE, eval_method=EvalMethod.LLM_JUDGE,
                      must_pass=True)
    (out,) = guard_security_gates([q], Mode.ADVERSARIAL)
    assert out.dimension is Dimension.UNSAFE_TOOL_USE      # gates are the point in probe mode


def test_prepare_rubric_normalizes_then_guards():
    # deterministic-without-CHECK on a CRITICAL dim: normalize -> judge, then guard -> reclassify.
    # (Uses UNSAFE_TOOL_USE, not SOURCE_FABRICATION — the latter now routes to the F3 source-check gate.)
    q = _q("x", Dimension.UNSAFE_TOOL_USE, EvalMethod.DETERMINISTIC, "no directive")
    (out,) = prepare_rubric([q], Mode.QUALITY)
    assert out.eval_method is EvalMethod.LLM_JUDGE
    assert out.dimension is Dimension.ANSWER_CORRECTNESS
