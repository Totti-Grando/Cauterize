"""Layer B -- Optimization Loop (optional). Dependency is one-way: B -> A only."""

from .lessons import dedup_and_prune
from .orchestrator import optimize
from .results import IterationRecord, OptimizationResult
from .rubric_critic import (
    RubricCritic,
    StubRubricCritic,
    critic_collector,
    defect_objective,
)
from .signals import Failure, collect_failures

__all__ = [
    "optimize",
    "dedup_and_prune",
    "collect_failures",
    "Failure",
    "IterationRecord",
    "OptimizationResult",
    "RubricCritic",
    "StubRubricCritic",
    "critic_collector",
    "defect_objective",
]
