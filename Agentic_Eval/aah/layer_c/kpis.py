"""Program KPI aggregator (G9).

Rolls a set of ``AssuranceRecord``s up into program-level KPIs: coverage, evidence completeness,
time-to-decision, re-evaluation rate, 2LoD challenge rate, decision quality, and evidence quality.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Optional, Sequence

from ..contracts import AssuranceRecord, LineOfDefence


@dataclass(frozen=True)
class ProgramKPIs:
    total_records: int
    pct_fully_evaluated: float        # disposition set AND at least one banded dimension
    pct_complete_evidence: float      # evidence links present
    pct_reevaluated_on_triggers: float  # a KRI raised a re-evaluation
    challenge_rate_2lod: float        # a 2nd-line reviewer is present
    decision_quality: float           # an explicit disposition (not None)
    evidence_quality: float           # evidence links + reviewers + attestation all present
    mean_time_to_decision_hours: Optional[float]  # last reviewer − produced_at (if datable)

    def as_dict(self) -> dict:
        return asdict(self)


def _fraction(pred, records) -> float:
    return (sum(1 for r in records if pred(r)) / len(records)) if records else 0.0


def _time_to_decision_hours(rec: AssuranceRecord) -> Optional[float]:
    if not rec.reviewers or not rec.produced_at:
        return None
    try:
        start = datetime.fromisoformat(rec.produced_at)
        ends = [datetime.fromisoformat(rv.timestamp) for rv in rec.reviewers if rv.timestamp]
    except ValueError:
        return None
    if not ends:
        return None
    return max((max(ends) - start).total_seconds() / 3600.0, 0.0)


def program_kpis(records: Sequence[AssuranceRecord]) -> ProgramKPIs:
    """Quarterly-style rollup over a set of assurance records."""
    records = list(records)
    n = len(records)

    def fully_evaluated(r: AssuranceRecord) -> bool:
        return r.disposition is not None and any(a.band is not None for a in r.dimensions)

    def has_2lod(r: AssuranceRecord) -> bool:
        return any(rv.lod is LineOfDefence.SECOND for rv in r.reviewers)

    def evidence_pack_complete(r: AssuranceRecord) -> bool:
        return bool(r.evidence_links) and bool(r.reviewers) and bool(r.attestation)

    times = [t for t in (_time_to_decision_hours(r) for r in records) if t is not None]

    return ProgramKPIs(
        total_records=n,
        pct_fully_evaluated=_fraction(fully_evaluated, records),
        pct_complete_evidence=_fraction(lambda r: bool(r.evidence_links), records),
        pct_reevaluated_on_triggers=_fraction(
            lambda r: any(k.reevaluate for k in r.kri_alerts), records),
        challenge_rate_2lod=_fraction(has_2lod, records),
        decision_quality=_fraction(lambda r: r.disposition is not None, records),
        evidence_quality=_fraction(evidence_pack_complete, records),
        mean_time_to_decision_hours=(round(sum(times) / len(times), 3) if times else None),
    )
