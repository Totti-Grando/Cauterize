"""Guardrails the harness builds in (spec v3 §9). Cross-cutting; used by the pipeline.

Four guards from §9 plus the question-quality dedup that feeds the aggregator's prune step:

1. ``prune_redundant`` -- principled dedup (§9, §7.2): per dimension, drop questions whose
   yes-rate is outside the healthy band or that are near-duplicates by pairwise phi
   correlation. Returns the *survivor* set the aggregator averages. Healthy mean off-diagonal
   phi is ~0.38; pairs above ``phi_threshold`` are collapsed.
2. ``numbers_equivalent`` -- numbers are not string-match (§9): "83rd minute" == "seven minutes
   remaining" in a 90-minute match. Compares with absolute/relative tolerance and an optional
   ``total`` for complementary quantities.
3. ``asserts_claim`` -- omission != hallucination (§9): the "supported?" question fires only on
   claims the response actually makes, so an omitted source fact is never scored as an error.
4. ``combine_runs`` -- determinism (§9, §10): average over 2 runs so borderline questions that
   flip between 0 and 1 are caught and resolved conservatively, rather than scored at random.
"""

from __future__ import annotations

import re
from typing import Iterable, Optional, Sequence

import numpy as np

from .contracts import Verdict


# --- 1. principled dedup (phi + yes-rate) -------------------------------------

def phi_correlation(x: Sequence[int], y: Sequence[int]) -> float:
    """Matthews / phi correlation between two binary verdict vectors.

    Returns 0.0 when either vector is constant (no variance to correlate).
    """

    a = np.asarray(x, dtype=float)
    b = np.asarray(y, dtype=float)
    if a.size != b.size or a.size == 0:
        raise ValueError("vectors must be non-empty and equal length")
    if a.std() == 0 or b.std() == 0:
        return 0.0
    return float(np.corrcoef(a, b)[0, 1])


def prune_redundant(
    question_ids: Sequence[str],
    verdict_matrix: Sequence[Sequence[int]],
    *,
    phi_threshold: float = 0.9,
    yes_rate_band: tuple[float, float] = (0.05, 0.95),
) -> set[str]:
    """Return the survivor question ids after §9 dedup.

    ``verdict_matrix`` is questions x samples (e.g. across tasks or runs). A question is
    dropped if its yes-rate (mean) falls outside ``yes_rate_band`` (it never discriminates),
    or if it correlates above ``phi_threshold`` with an already-kept question (redundant).
    With a single sample column, phi is undefined, so only the yes-rate filter applies.
    """

    if len(question_ids) != len(verdict_matrix):
        raise ValueError("question_ids and verdict_matrix must align")

    mat = [list(row) for row in verdict_matrix]
    low, high = yes_rate_band

    # Yes-rate filter first.
    surviving: list[int] = []
    for i, row in enumerate(mat):
        if not row:
            surviving.append(i)
            continue
        yes_rate = sum(row) / len(row)
        if low <= yes_rate <= high:
            surviving.append(i)

    # Phi-redundancy filter: keep the first of any highly-correlated pair.
    kept: list[int] = []
    for i in surviving:
        redundant = False
        for j in kept:
            if abs(phi_correlation(mat[i], mat[j])) >= phi_threshold:
                redundant = True
                break
        if not redundant:
            kept.append(i)

    return {question_ids[i] for i in kept}


def kept_after_phi_dedup(
    dim_of: dict[str, object],
    scores_by_id: dict[str, Sequence[int]],
    *,
    phi_threshold: float = 0.9,
) -> set[str]:
    """Per-dimension phi de-dup: keep the first of any near-duplicate pair (|phi| >= threshold).

    ``dim_of`` maps question id -> dimension; ``scores_by_id`` maps question id -> its verdicts
    across runs/samples. Two checks that correlate above ``phi_threshold`` measure the same facet,
    so keeping both double-weights it in the uniform per-dimension mean (F8). Correlation needs
    variance across samples: with one sample (or a constant vector) phi is 0 and nothing is
    dropped — so single-run deterministic evaluations are unaffected.
    """
    from collections import defaultdict

    dim_qs: dict[object, list[str]] = defaultdict(list)
    for qid, dim in dim_of.items():
        dim_qs[dim].append(qid)

    kept: set[str] = set()
    for _dim, qids in dim_qs.items():
        kept_here: list[str] = []
        for qid in qids:
            row = list(scores_by_id.get(qid, []))
            redundant = False
            for k in kept_here:
                other = list(scores_by_id.get(k, []))
                if len(other) == len(row) and row and abs(phi_correlation(row, other)) >= phi_threshold:
                    redundant = True
                    break
            if not redundant:
                kept_here.append(qid)
        kept.update(kept_here)
    return kept


# --- 2. numeric semantic equivalence ------------------------------------------

_NUM_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
    "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
    "seventy": 70, "eighty": 80, "ninety": 90, "hundred": 100,
}


def extract_numbers(text: str) -> list[float]:
    """Pull numeric values from text, including simple number-words."""

    nums = [float(m) for m in re.findall(r"-?\d+(?:\.\d+)?", text)]
    for word, val in _NUM_WORDS.items():
        if re.search(rf"\b{word}\b", text, re.IGNORECASE):
            nums.append(float(val))
    return nums


def numbers_equivalent(
    a: float,
    b: float,
    *,
    abs_tol: float = 1e-9,
    rel_tol: float = 0.01,
    total: Optional[float] = None,
) -> bool:
    """True if a and b are the same quantity within tolerance, or complementary to ``total``.

    The ``total`` argument handles "83rd minute" vs "seven minutes remaining" in a 90-minute
    match: 83 and 7 are equivalent because 83 + 7 == 90.
    """

    def close(x: float, y: float) -> bool:
        return abs(x - y) <= max(abs_tol, rel_tol * max(abs(x), abs(y)))

    if close(a, b):
        return True
    if total is not None and close(a, total - b):
        return True
    return False


# --- 3. omission != hallucination ---------------------------------------------

def asserts_claim(claim: str, response: str, *, min_overlap: float = 0.6) -> bool:
    """Heuristic: does the response actually make ``claim`` (so a "supported?" check should fire)?

    Omission is not hallucination -- a source fact the summary simply leaves out must not be
    scored as a factual error. We approximate "the summary makes this claim" by content-word
    overlap between the claim and the response. Replace with an NLI entailment check when the
    nli scorer is wired for this path.
    """

    def content_words(s: str) -> set[str]:
        return {w for w in re.findall(r"[a-z0-9]+", s.lower()) if len(w) > 2}

    claim_words = content_words(claim)
    if not claim_words:
        return False
    overlap = len(claim_words & content_words(response)) / len(claim_words)
    return overlap >= min_overlap


# --- 4. determinism: average over 2 runs --------------------------------------

def combine_runs(runs: Sequence[Sequence[Verdict]]) -> list[Verdict]:
    """Combine repeated runs into one verdict list, resolving borderline flips conservatively.

    For each question, average the scores across runs (§9/§10 "average over 2 runs"). A question
    that agrees across all runs keeps that score; a question that *flips* (mean strictly between
    0 and 1) is resolved to 0 (conservative -- a borderline pass is not credited) and its
    instability is recorded in the explanation so the loop can see it.
    """

    if not runs:
        return []
    by_q: dict[str, list[Verdict]] = {}
    order: list[str] = []
    for run in runs:
        for v in run:
            if v.question_id not in by_q:
                order.append(v.question_id)
            by_q.setdefault(v.question_id, []).append(v)

    combined: list[Verdict] = []
    for qid in order:
        verdicts = by_q[qid]
        mean = sum(v.score for v in verdicts) / len(verdicts)
        if mean in (0.0, 1.0):
            combined.append(verdicts[0].model_copy(update={"score": int(mean)}))
        else:
            note = f"unstable across {len(verdicts)} runs (mean={mean:.2f}); resolved to 0"
            base = next((v for v in verdicts if v.score == 0), verdicts[0])
            combined.append(
                base.model_copy(update={"score": 0, "explanation": f"{base.explanation} [{note}]"})
            )
    return combined


def mean_yes_rates(verdict_matrix: Iterable[Sequence[int]]) -> list[float]:
    """Per-question yes-rate across samples -- the spread input to the §9 dedup check."""

    return [sum(row) / len(row) if row else 0.0 for row in verdict_matrix]


# --- 5. leniency / yes-bias monitor (F6) --------------------------------------

def flag_lenient_dimensions(
    yes_rate_summary: dict[str, float], *, ceiling: float = 0.95
) -> list[str]:
    """Dimensions whose checks nearly all pass (>= ceiling) — near-degenerate / yes-biased.

    "yes" = pass on our binary checks, so an agreeable judge inflates every score. A dimension
    whose pass-rate sits at or above ``ceiling`` isn't discriminating and should be reviewed
    (the checks may be trivially satisfiable, or the judge may be too lenient). This is a
    monitoring signal surfaced from ``AuditRecord.yes_rate_summary``, not a hard gate.
    """
    return [dim for dim, rate in yes_rate_summary.items() if rate >= ceiling]
