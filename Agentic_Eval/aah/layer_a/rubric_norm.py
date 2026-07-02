"""Rubric normalization — route each check to a scorer that actually grades the response.

A live run surfaced two mis-routings the fixtures hid:
1. ``deterministic`` questions with no ``CHECK:`` directive abstain (free score=1).
2. ``nli`` questions on holistic dimensions (relevance, completeness) grade the *context*
   (the source), not the response -- so a refusal still passed.

The fix: a check keeps its scorer only if it carries a concrete, self-contained directive the
scorer can execute -- a ``CHECK:`` for ``deterministic`` or an ``ATTACK:`` for
``injection_detector``. Everything else is routed to ``llm_judge``, which answers the yes/no
question *about the response* (taking the source as context). This makes the score reflect
what the model actually produced. (A response-aware NLI backend -- MiniCheck-style claim
extraction -- can later reclaim the ``nli`` path for grounded faithfulness checks.)
"""

from __future__ import annotations

from ..config import POLICY_TABLE
from ..contracts import BinaryQuestion, Dimension, EvalMethod, Mode, Tier

#: CRITICAL (gating) dimensions, derived from the frozen policy table so it stays in sync.
_CRITICAL_DIMENSIONS = frozenset(d for d, t in POLICY_TABLE.items() if t is Tier.CRITICAL)

#: Where a mis-tagged security check lands in quality mode -- a scored, non-gating dimension.
_FALLBACK_DIMENSION = Dimension.ANSWER_CORRECTNESS


def _directive(q: BinaryQuestion) -> str:
    """The machine directive for a check: the dedicated field, else the legacy prose field."""
    return (q.check_directive or q.violation_example or "").strip()


def normalize_rubric(rubric: list[BinaryQuestion]) -> list[BinaryQuestion]:
    """Re-route checks without an executable directive to ``llm_judge``.

    Deterministic (``CHECK:``) and injection (``ATTACK:``) checks are kept ONLY when they carry
    the matching directive — read from ``check_directive`` first, falling back to the legacy
    ``violation_example``. This is what lets an LLM-generated rubric actually exercise the
    deterministic/injection scorers instead of collapsing to a single judge (audit finding #1).
    ``nli``/``source_fetch`` are intentionally routed to ``llm_judge`` here: the current NLI
    backend grades the *context*, not the response, so the judge (which is response-aware) is the
    faithful scorer until a response-aware NLI backend lands. See docs/correctness-review-findings.md.
    """

    out: list[BinaryQuestion] = []
    for q in rubric:
        directive = _directive(q)
        if q.dimension is Dimension.SOURCE_FABRICATION or q.eval_method is EvalMethod.SOURCE_CHECK:
            # F3: the fabrication gate is ALWAYS the deterministic source-check scorer — never
            # the LLM judge or source_fetch.
            target = EvalMethod.SOURCE_CHECK
        elif q.eval_method is EvalMethod.DETERMINISTIC and directive.startswith("CHECK:"):
            target = EvalMethod.DETERMINISTIC
        elif q.eval_method is EvalMethod.INJECTION_DETECTOR and directive.startswith("ATTACK:"):
            target = EvalMethod.INJECTION_DETECTOR
        else:
            target = EvalMethod.LLM_JUDGE
        out.append(q if target is q.eval_method else q.model_copy(update={"eval_method": target}))
    return out


def _has_executable_directive(q: BinaryQuestion) -> bool:
    """True if the check gates on a concrete rule, not a free-form judge call."""
    directive = _directive(q)
    return (
        q.eval_method is EvalMethod.SOURCE_CHECK  # deterministic fabrication gate
        or (q.eval_method is EvalMethod.DETERMINISTIC and directive.startswith("CHECK:"))
        or (q.eval_method is EvalMethod.INJECTION_DETECTOR and directive.startswith("ATTACK:"))
    )


def guard_security_gates(rubric: list[BinaryQuestion], mode: Mode) -> list[BinaryQuestion]:
    """Stop the LLM rubric generator from tripping gates with ordinary quality checks.

    A free-choosing generator produces two gate-tripping mistakes:

    1. It mis-files helpfulness checks under CRITICAL security dimensions (e.g. tagging "is the
       answer specific enough?" as ``unsafe_tool_use``), which gates the run to FAIL (§7.4) for
       the wrong reason. In quality mode a CRITICAL dimension is legitimate only on a real
       security probe (an ``injection_detector`` check); any other check tagged into one is
       reclassified to a scored, non-gating quality dimension.
    2. It marks ordinary quality checks ``must_pass``, and a must-pass 0 also hard-gates (§7.4).
       In quality mode ``must_pass`` is honored only for checks with a concrete executable
       directive (``deterministic`` CHECK: / ``injection_detector`` ATTACK:); on free-form judge
       checks it is cleared, so a single noisy judgement can't fail the whole run.

    In adversarial / hybrid mode the gates are the point, so the rubric is left untouched.
    """

    if mode is not Mode.QUALITY:
        return rubric

    out: list[BinaryQuestion] = []
    for q in rubric:
        updates: dict = {}
        if q.dimension in _CRITICAL_DIMENSIONS and q.eval_method not in (
            EvalMethod.INJECTION_DETECTOR, EvalMethod.SOURCE_CHECK
        ):
            updates["dimension"] = _FALLBACK_DIMENSION       # misfiled security dimension
        if q.must_pass and not _has_executable_directive(q):
            updates["must_pass"] = False                     # no hard gate from a judge check
        out.append(q.model_copy(update=updates) if updates else q)
    return out


def prepare_rubric(rubric: list[BinaryQuestion], mode: Mode) -> list[BinaryQuestion]:
    """Full rubric hygiene: route checks to a real scorer, then guard the security gates."""

    return guard_security_gates(normalize_rubric(rubric), mode)
