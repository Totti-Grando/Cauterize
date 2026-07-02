"""The improvement loop (spec §8). [single-owner, high risk]

Layer B wraps Layer A: it runs A over a seed set with the current ``P_Q``, collects the
failure signal paired with explanations, generalizes lessons, dedups/prunes them (discarding
structural lessons as findings), patches ``P_Q`` under the length budget, and loops until it
converges. Dependency is one-way B -> A: the orchestrator reaches Layer A only through the
injected ``run_layer_a`` callable, so it never imports Layer A internals here.

Convergence (§8 step 5): stop on no-new-signal, reference-match within epsilon, no promptable
lessons, a stable prompt, or max iterations. The best iteration (highest mean overall — the
held-out-data stand-in) is selected and returned.
"""

from __future__ import annotations

import inspect
from typing import Any, Awaitable, Callable, Optional

from ..contracts import AuditRecord, Mode
from .lessons import dedup_and_prune
from .notetaker import NoteTaker
from .results import IterationRecord, OptimizationResult
from .signals import collect_failures
from .updater import Updater

# A Layer A driver: given the current P_Q and iteration index, run A over the seeds.
RunLayerA = Callable[[str, int], Awaitable[list[AuditRecord]]]


def _mean_overall(records: list[AuditRecord]) -> float:
    if not records:
        return 0.0
    return sum(r.scores.overall for r in records) / len(records)


async def optimize(
    *,
    initial_p_q: str,
    run_layer_a: RunLayerA,
    notetaker: NoteTaker,
    updater: Updater,
    mode: Mode = Mode.QUALITY,
    max_iterations: int = 5,
    budget: int = 2000,
    reference_overall: Optional[float] = None,
    epsilon: float = 0.02,
    collect: Optional[Callable[[list[AuditRecord]], Any]] = None,
    objective_fn: Optional[Callable[[list[AuditRecord], list], float]] = None,
) -> OptimizationResult:
    """Run the §8 loop and return the best iteration's prompt + the full trail.

    ``collect`` overrides how the failure signal is derived from the iteration's records
    (default: score-0 / attack_success verdicts). It may be sync or async. ``objective_fn``
    overrides what "best" means (default: quality maximizes mean overall; adversarial maximizes
    landed attacks). Rubric-quality loop learning injects a critic-based ``collect`` plus an
    objective that minimizes defects.
    """

    adversarial = mode is Mode.ADVERSARIAL

    def _default_objective(records: list[AuditRecord], failures: list) -> float:
        # quality tunes toward a higher overall; adversarial toward more landed attacks (§1, §8).
        return float(len(failures)) if adversarial else _mean_overall(records)

    score_objective = objective_fn or _default_objective

    p_q = initial_p_q
    iterations: list[IterationRecord] = []
    findings_all = []
    best_p_q, best_iteration = initial_p_q, -1
    best_mean, best_objective = 0.0, float("-inf")
    converged = "max-iterations"

    for i in range(max_iterations):
        # Run Layer A with the current prompt; derive this iteration's failure signal.
        records = await run_layer_a(p_q, i)
        mean_overall = _mean_overall(records)
        if collect is None:
            failures = collect_failures(records)
        else:
            result = collect(records)
            failures = await result if inspect.isawaitable(result) else result
        objective = score_objective(records, failures)

        # Generalize + classify lessons for this iteration's signal.
        lessons = notetaker.take_notes(failures, mode) if failures else []
        promptable, structural = dedup_and_prune(lessons)
        findings_all.extend(structural)

        iterations.append(
            IterationRecord(
                iteration=i,
                prompt_version=f"P_Q@v{i}",
                p_q=p_q,
                mean_overall=mean_overall,
                num_failures=len(failures),
                num_promptable_lessons=len(promptable),
                findings=list(structural),
            )
        )

        # Track the best iteration on the mode's objective (held-out stand-in).
        if objective > best_objective:
            best_objective, best_mean, best_iteration, best_p_q = objective, mean_overall, i, p_q

        # Convergence checks (§8 step 5).
        if not failures:
            converged = "no-new-signal"
            break
        if reference_overall is not None and abs(mean_overall - reference_overall) <= epsilon:
            converged = "reference-match"
            break
        if not promptable:
            converged = "no-promptable-lessons"
            break

        # Patch P_Q under the length budget (§9 bloat guard inside the updater).
        new_p_q = updater.patch(p_q, promptable, budget=budget)
        if new_p_q == p_q:
            converged = "prompt-stable"
            break
        p_q = new_p_q

    return OptimizationResult(
        best_p_q=best_p_q,
        best_iteration=best_iteration,
        best_mean_overall=best_mean if best_mean != float("-inf") else 0.0,
        converged_reason=converged,
        iterations=iterations,
        findings=findings_all,
        initial_p_q=initial_p_q,
        final_p_q=p_q,
        reference_overall=reference_overall,
    )
