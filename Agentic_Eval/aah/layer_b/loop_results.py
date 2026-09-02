"""Layer B result types. Not part of the frozen §4 contracts (those are Layer A's)."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict

from ..contracts import Lesson


class IterationRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    iteration: int
    prompt_version: str
    p_q: str
    mean_overall: float
    num_failures: int
    num_promptable_lessons: int
    findings: list[Lesson]  # structural lessons logged this iteration (not injected)


class OptimizationResult(BaseModel):
    """Outcome of an optimisation run (spec §8 step 5)."""

    model_config = ConfigDict(frozen=True)

    best_p_q: str
    best_iteration: int
    best_mean_overall: float
    converged_reason: str
    iterations: list[IterationRecord]
    findings: list[Lesson]  # all structural lessons = provider capability findings (§8, §9)
    initial_p_q: str
    final_p_q: str
    reference_overall: Optional[float] = None
