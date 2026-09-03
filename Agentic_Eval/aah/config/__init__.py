"""WeightConfig loading + the frozen tier policy table (spec §7)."""

from .loader import (
    default_risk_policy,
    default_weight_config,
    load_risk_policy,
    load_weight_config,
)
from .policy import (
    DEFAULT_GATE_THRESHOLD,
    DEFAULT_GATE_THRESHOLDS,
    OWASP_LLM_TOP10,
    POLICY_TABLE,
)

__all__ = [
    "default_weight_config",
    "load_weight_config",
    "default_risk_policy",
    "load_risk_policy",
    "POLICY_TABLE",
    "DEFAULT_GATE_THRESHOLD",
    "DEFAULT_GATE_THRESHOLDS",
    "OWASP_LLM_TOP10",
]
