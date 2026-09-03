"""3LoD + 2LoD challenge + attestation (G7).

Records reviewer metadata by line of defence and wires the **cross-family reference evaluator** as
the automated 2nd-line challenge on the gating dimensions: when the run's judge and the
system-under-test are NOT the same model family (``provenance.same_family_judge is False``), the
independent judgement counts as a cleared 2LoD challenge; a same-family judge does not.

Senior-management attestation is captured verbatim by the caller and stored immutably on the record.
"""

from __future__ import annotations

from ..contracts import AuditRecord, LineOfDefence, Reviewer


def reviewer(id: str, lod: LineOfDefence, timestamp: str) -> Reviewer:
    """Construct a reviewer entry for a given line of defence."""
    return Reviewer(id=id, lod=lod, timestamp=timestamp)


def automated_2lod_cleared(audit: AuditRecord) -> bool:
    """True when a cross-family reference judged the run (an independent 2LoD challenge).

    The gate scorers are only credibly challenged by a DIFFERENT model family — a same-family judge
    is not an independent second line. F1 provenance already records this as ``same_family_judge``.
    """
    prov = audit.provenance
    # A challenge exists only if there is a real provider identity and the judge is cross-family.
    has_sut = bool(prov.provider.backend or prov.provider.model)
    return has_sut and not prov.same_family_judge


def cross_family_challenge_reviewer(audit: AuditRecord, timestamp: str) -> Reviewer | None:
    """A 2LoD reviewer entry for the automated cross-family challenge, if one was performed."""
    if not automated_2lod_cleared(audit):
        return None
    ev = audit.provenance.evaluator
    who = f"cross-family-ref:{ev.backend or 'eval'}/{ev.model or 'model'}"
    return Reviewer(id=who, lod=LineOfDefence.SECOND, timestamp=timestamp)


def challenge_rate(reviewers) -> float:
    """Fraction of reviewer entries that are 2nd-line challenges (program-KPI input)."""
    reviewers = list(reviewers)
    if not reviewers:
        return 0.0
    return sum(1 for r in reviewers if r.lod is LineOfDefence.SECOND) / len(reviewers)
