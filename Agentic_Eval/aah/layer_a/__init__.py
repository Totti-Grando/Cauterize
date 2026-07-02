"""Layer A -- Evaluator Core (standalone). Imports nothing from Layer B."""

from .aggregator import aggregate, tierweight
from .audit import AuditLog
from .pipeline import run_once

__all__ = ["aggregate", "tierweight", "AuditLog", "run_once"]
