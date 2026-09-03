"""Layer C — governance.

Turns evaluator ``AuditRecord``s into governed, risk-scored, disposition-carrying
``AssuranceRecord``s under a 3LoD model (master build plan, Stage 1).

Phases 1–3 (implemented): the contracts foundation + ``to_assurance_record`` (metrics, G/A/R + L×I
banding, disposition, monitoring/trend/KRIs, 3LoD/2LoD challenge, anchors, retention, coverage), the
program-KPI rollup, and the immutable evidence store + export. Phase 4 (G11–G16) fills the
completeness items — see the module docstrings.
"""

from .contestability import apply_override, effective_disposition
from .evidence import AssuranceStore, ImmutableViolation, governance_template
from .explainability import explainability_score, reasoning_fidelity
from .governance import default_coverage_scope, to_assurance_record
from .harm import harm_rate, is_harmful
from .kpis import ProgramKPIs, program_kpis
from .monitoring import MonitoringStore, evaluate_kris
from .omission import omission_metric, wilson_interval
from .reliability import ReliabilityItem, evaluator_reliability

__all__ = [
    "to_assurance_record",
    "default_coverage_scope",
    "MonitoringStore",
    "evaluate_kris",
    "program_kpis",
    "ProgramKPIs",
    "AssuranceStore",
    "ImmutableViolation",
    "governance_template",
    # Phase 4
    "evaluator_reliability",
    "ReliabilityItem",
    "reasoning_fidelity",
    "explainability_score",
    "harm_rate",
    "is_harmful",
    "omission_metric",
    "wilson_interval",
    "apply_override",
    "effective_disposition",
]
