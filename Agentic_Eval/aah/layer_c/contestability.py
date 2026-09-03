"""Contestability / override path (G15).

A machine disposition must be challengeable and overridable — not final-by-machine. The accountable
owner can contest a decision (typically to ``Accept-risk`` with attestation) and 2LoD can challenge
it. Every override is append-only: it records the original disposition, the new one, a rationale, the
reviewer, and a timestamp; it never erases the original, and all overrides remain visible to 3LoD.
"""

from __future__ import annotations

from typing import Optional

from ..contracts import AssuranceRecord, Disposition, LineOfDefence, Override


def effective_disposition(record: AssuranceRecord) -> Optional[Disposition]:
    """The disposition in force now: the latest override if any, else the machine decision."""
    return record.overrides[-1].new_disposition if record.overrides else record.disposition


def apply_override(
    record: AssuranceRecord,
    *,
    new_disposition: Disposition,
    rationale: str,
    reviewer_id: str,
    lod: LineOfDefence,
    timestamp: str,
) -> AssuranceRecord:
    """Return a new record with an appended override. The original disposition is preserved.

    Raises if there is no current disposition to contest, or if the rationale is empty (an override
    without a stated reason is not auditable).
    """
    original = effective_disposition(record)
    if original is None:
        raise ValueError("no disposition to contest")
    if not rationale.strip():
        raise ValueError("an override requires a rationale")
    override = Override(
        original_disposition=original, new_disposition=new_disposition, rationale=rationale,
        reviewer_id=reviewer_id, timestamp=timestamp, lod=lod,
    )
    return record.model_copy(update={"overrides": [*record.overrides, override]})
