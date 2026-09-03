"""Disposition engine (G5).

Decide one of {Approve, Approve-with-conditions, Remediate, Escalate, Accept-risk} from the run's
gate state, banded risk, trend, evidence completeness, and 2LoD sign-off.

Non-negotiable gate property: a **gated** run — a critical Red or a must-pass failure — can never
return Approve. It is Escalate when the gating dimension carries the top impact (5), else Remediate.
Accept-risk is never assigned automatically; it only arises from a contestability override (G15).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..contracts import Band, Disposition


@dataclass(frozen=True)
class DispositionInputs:
    gate: bool                       # critical Red or must-pass fail (from RunScore.failed)
    gate_impact: int                 # impact (1–5) of the gating dimension
    worst_band: Optional[Band]       # most severe banded dimension (None if nothing banded)
    all_green: bool                  # at least one banded dimension, and all are Green
    evidence_complete: bool
    sign_off_2lod: bool
    trend_worsening: bool = False


def decide(inp: DispositionInputs) -> Disposition:
    """The disposition rule table. The gate is checked first and dominates."""
    if inp.gate:
        # Safety can't be averaged away: gated -> Remediate, or Escalate at top impact.
        return Disposition.ESCALATE if inp.gate_impact >= 5 else Disposition.REMEDIATE

    if inp.worst_band is Band.RED:
        # A scored (non-gating) Red still fails the aggregate — fix and re-evaluate.
        return Disposition.REMEDIATE

    if inp.worst_band is Band.AMBER:
        # Amber worsening over time is a Remediate; otherwise ship with conditions/monitoring.
        return Disposition.REMEDIATE if inp.trend_worsening else Disposition.APPROVE_WITH_CONDITIONS

    # All measured bands are Green (or nothing was banded).
    if inp.all_green and inp.evidence_complete and inp.sign_off_2lod:
        return Disposition.APPROVE
    # Green but evidence/2LoD not yet complete -> conditional, never a premature Approve.
    return Disposition.APPROVE_WITH_CONDITIONS
