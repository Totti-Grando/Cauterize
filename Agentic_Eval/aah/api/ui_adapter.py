"""Map the engine's AuditRecord onto the shapes the React pages consume.

The UI thinks in {verdict, grounded, sourceGroundedness, shortfalls, points, evidence};
the engine thinks in {verdicts (0/1 + explanation), per-dimension scores, gating}. This is
the single translation layer between the two vocabularies, so the pages never see raw
engine contracts and the engine never learns about UI wording.
"""

from __future__ import annotations

from ..contracts import AuditRecord, BinaryQuestion, Dimension, Subtype, Verdict

# Engine failure subtype -> the UI's coarse shortfall tag vocabulary.
_SUBTYPE_TO_SHORTFALL: dict[Subtype, str] = {
    Subtype.UNSUPPORTED: "unsupported_claim",
    Subtype.FABRICATION: "unsupported_claim",
    Subtype.FABRICATED_SOURCE: "unsupported_claim",
    Subtype.ENTITY_ERROR: "contradiction",
    Subtype.NUMBER_ERROR: "contradiction",
    Subtype.CAUSAL_ERROR: "contradiction",
    Subtype.CONFLATION: "contradiction",
    Subtype.MISATTRIBUTION: "not_grounded_in_context",
    Subtype.ABSTENTION_FAILURE: "missing_information",
}
# Fallback by dimension when the subtype is generic (OTHER).
_DIMENSION_TO_SHORTFALL: dict[Dimension, str] = {
    Dimension.FACTUAL_CONSISTENCY: "not_grounded_in_context",
    Dimension.COMPLETENESS: "missing_information",
    Dimension.ANSWER_CORRECTNESS: "contradiction",
    Dimension.SOURCE_FABRICATION: "unsupported_claim",
}


def _is_abstain(explanation: str) -> bool:
    """True when the deterministic scorer declined to grade (no runnable check)."""
    e = (explanation or "").lower()
    return (
        e.startswith("no deterministic check specified")
        or e.startswith("unknown deterministic check")
        or "could not run" in e
    )


def _shortfall_for(q: BinaryQuestion) -> str | None:
    return _SUBTYPE_TO_SHORTFALL.get(q.subtype) or _DIMENSION_TO_SHORTFALL.get(q.dimension)


def audit_to_evaluation(record: AuditRecord, meta: dict) -> dict:
    """Convert one AuditRecord (+ per-case UI metadata) into a UI evaluation object.

    ``meta`` carries the UI-only fields the engine has no concept of:
    ``id, questionId, provider, persona, category, expected, evidence``.
    """
    rubric_by_id: dict[str, BinaryQuestion] = {q.id: q for q in record.rubric}
    verdicts: list[Verdict] = list(record.verdicts)
    by_dim = {d.dimension: d for d in record.scores.per_dimension}

    failed = [(rubric_by_id[v.question_id], v) for v in verdicts if v.score == 0 and v.question_id in rubric_by_id]
    abstained = [v for v in verdicts if _is_abstain(v.explanation)]
    all_abstained = bool(verdicts) and len(abstained) == len(verdicts)

    overall = record.scores.overall

    # --- headline verdict ---
    if record.scores.failed:
        verdict = "incorrect"
    elif all_abstained or not verdicts:
        verdict = "unverifiable"
    elif overall >= 0.85:
        verdict = "correct"
    elif overall >= 0.5:
        verdict = "partial"
    else:
        verdict = "incorrect"

    # --- groundedness from the factual-consistency dimension ---
    fc = by_dim.get(Dimension.FACTUAL_CONSISTENCY)
    if fc is not None:
        grounded = fc.score >= 0.999
        source_groundedness = "grounded" if grounded else ("partial" if fc.score > 0 else "ungrounded")
    else:
        grounded = verdict == "correct"
        source_groundedness = "grounded" if grounded else "partial"
    if verdict == "unverifiable":
        grounded = False
        source_groundedness = "partial"

    # --- reasoning quality band ---
    if record.scores.failed or verdict == "incorrect":
        reasoning = "Weak"
    elif verdict == "unverifiable":
        reasoning = "Adequate"
    else:
        reasoning = "Strong" if overall >= 0.85 else "Adequate"

    # --- shortfalls + categorized points from the failed checks ---
    shortfalls: list[str] = []
    missing_points: list[str] = []
    incorrect_points: list[str] = []
    for q, _v in failed:
        tag = _shortfall_for(q)
        if tag and tag not in shortfalls:
            shortfalls.append(tag)
        if q.dimension in (Dimension.COMPLETENESS, Dimension.ABSTENTION_CALIBRATION) or q.subtype is Subtype.ABSTENTION_FAILURE:
            missing_points.append(q.text)
        else:
            incorrect_points.append(q.text)

    n_total = len(verdicts)
    n_pass = sum(1 for v in verdicts if v.score == 1)
    if record.scores.failed:
        gate = record.scores.gated_by.value.replace("_", " ") if record.scores.gated_by else "a must-pass check"
        summary = f"Gated to FAIL by {gate}. {n_pass}/{n_total} rubric checks passed."
    elif verdict == "unverifiable":
        summary = "Answer requires holistic/source verification the offline scorers cannot perform. Flag for human review."
    else:
        summary = f"{n_pass}/{n_total} rubric checks passed (overall {overall:.2f}). Verdict: {verdict}."

    return {
        "id": meta["id"],
        "questionId": meta.get("questionId", meta["id"]),
        "question": record.question,
        "persona": meta.get("persona"),
        "category": meta.get("category"),
        "provider": meta.get("provider", "RavenPack"),
        "providerAnswer": record.response,
        "expectedAnswer": meta.get("expected", ""),
        "verdict": verdict,
        "grounded": grounded,
        "sourceGroundedness": source_groundedness,
        "reasoningQuality": reasoning,
        "shortfalls": shortfalls,
        "missingPoints": missing_points,
        "incorrectPoints": incorrect_points,
        "extraPoints": [],
        "finalSummary": summary,
        "evidence": meta.get("evidence", []),
        # engine-native extras (handy for debugging / a future "raw audit" panel)
        "overall": round(overall, 4),
        "failed": record.scores.failed,
        # Rubric + per-dimension breakdown so the UI can show WHAT is being evaluated and a
        # simplified evaluator view (requirement -> question breakdown, tiers, gate).
        "rubric": _rubric_breakdown(record),
        "perDimension": _per_dimension(record),
        "gatedBy": record.scores.gated_by.value if record.scores.gated_by else None,
        # Who judged / who was judged (F1) — for the evaluator-details view.
        "evaluatorAgent": {"backend": record.provenance.evaluator.backend,
                           "model": record.provenance.evaluator.model},
        "providerAgent": {"backend": record.provenance.provider.backend,
                          "model": record.provenance.provider.model},
        "sameFamilyJudge": record.provenance.same_family_judge,
        "mode": record.mode.value,
    }


def _rubric_breakdown(record: AuditRecord) -> list[dict]:
    """Group the rubric by requirement, each check carrying its tier + verdict + reason."""
    v_by_id = {v.question_id: v for v in record.verdicts}
    tiers = record.weight_config.tiers
    groups: list[dict] = []
    index: dict[str, int] = {}
    for q in record.rubric:
        key = q.requirement_text or q.requirement_id or q.id
        if key not in index:
            index[key] = len(groups)
            groups.append({"requirement": q.requirement_text or "(unspecified requirement)", "checks": []})
        v = v_by_id.get(q.id)
        tier = tiers.get(q.dimension)
        groups[index[key]]["checks"].append({
            "id": q.id,
            "text": q.text,
            "dimension": q.dimension.value,
            "tier": tier.value if tier else "",
            "eval_method": q.eval_method.value,
            "must_pass": q.must_pass,
            "score": v.score if v else None,
            "reason": v.explanation if v else "",
            "attack_success": v.attack_success if v else None,
        })
    return groups


def _per_dimension(record: AuditRecord) -> list[dict]:
    return [
        {"dimension": d.dimension.value, "tier": d.tier.value, "gating": d.gating,
         "score": round(d.score, 4), "weight": round(d.weight, 4)}
        for d in record.scores.per_dimension
    ]
