"""Regulatory anchor map (G8).

Stamps the framework-level regulatory anchors per dimension into the record (NIST AI RMF / ISO 42001
& 23894 / OSFI / Fed SR 11-7 / BIS / GDPR DPIA / OWASP LLM). The source tables live in
``config/governance_policy.py``. A dimension with no anchor is a WARNING, not a hard failure.
"""

from __future__ import annotations

from ..contracts import Dimension, RiskPolicy
from ..logging_config import get_logger

log = get_logger("layer_c.anchors")


def anchors_for(dimension: Dimension, policy: RiskPolicy) -> list[str]:
    """The regulatory anchors a dimension carries under ``policy`` (warns if none)."""
    dp = policy.dimensions.get(dimension)
    anchors = list(dp.anchors) if dp else []
    if not anchors:
        log.warning("dimension %s has no regulatory anchor mapped", dimension.value)
    return anchors
