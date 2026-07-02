"""F10: the frozen policy holds the full dimension set with CRITICAL gates mapped to OWASP LLM Top 10."""

from __future__ import annotations

from aah.config import DEFAULT_GATE_THRESHOLDS, OWASP_LLM_TOP10, POLICY_TABLE
from aah.contracts import Dimension, Tier


def test_all_dimensions_are_tiered():
    # Every frozen dimension must have a tier (no gaps in the policy table).
    assert set(POLICY_TABLE) == set(Dimension)


def test_critical_gates_map_to_owasp_top10():
    criticals = {d for d, t in POLICY_TABLE.items() if t is Tier.CRITICAL}
    # Every CRITICAL gate has an OWASP LLM Top-10 rationale, and vice versa.
    assert set(OWASP_LLM_TOP10) == criticals
    assert all(v.startswith("LLM") for v in OWASP_LLM_TOP10.values())


def test_every_critical_dimension_has_a_gate_threshold():
    criticals = {d for d, t in POLICY_TABLE.items() if t is Tier.CRITICAL}
    assert set(DEFAULT_GATE_THRESHOLDS) == criticals
    assert all(v == 1.0 for v in DEFAULT_GATE_THRESHOLDS.values())
