"""Guardrail behaviours (spec §9)."""

from __future__ import annotations

from aah.guards import (
    asserts_claim,
    combine_runs,
    extract_numbers,
    numbers_equivalent,
    phi_correlation,
    prune_redundant,
)
from tests.conftest import make_verdict


# --- dedup --------------------------------------------------------------------

def test_phi_is_zero_for_constant_vector():
    assert phi_correlation([1, 1, 1], [1, 0, 1]) == 0.0


def test_prune_drops_outside_yes_rate_band():
    # q_always_yes is uninformative (yes-rate 1.0) -> dropped; q_mixed kept.
    ids = ["q_always_yes", "q_mixed"]
    matrix = [[1, 1, 1, 1], [1, 0, 1, 0]]
    kept = prune_redundant(ids, matrix, yes_rate_band=(0.05, 0.95))
    assert kept == {"q_mixed"}


def test_prune_collapses_correlated_pair():
    ids = ["a", "b"]
    matrix = [[1, 0, 1, 0], [1, 0, 1, 0]]  # identical -> phi 1.0
    kept = prune_redundant(ids, matrix, phi_threshold=0.9)
    assert kept == {"a"}  # first of the pair survives


# --- numeric equivalence ------------------------------------------------------

def test_number_words_and_complement():
    assert 83.0 in extract_numbers("scored in the 83rd minute")
    assert 7.0 in extract_numbers("seven minutes remaining")
    # 83rd minute == seven minutes remaining, in a 90-minute match.
    assert numbers_equivalent(83, 7, total=90)
    assert not numbers_equivalent(83, 7)  # not equal without the complement context


def test_relative_tolerance():
    assert numbers_equivalent(100.0, 100.5, rel_tol=0.01)
    assert not numbers_equivalent(100.0, 110.0, rel_tol=0.01)


# --- omission != hallucination ------------------------------------------------

def test_asserts_claim_only_when_response_makes_it():
    response = "The company reported record revenue in the fourth quarter."
    assert asserts_claim("record revenue in the fourth quarter", response)
    # A source fact the summary omits must not fire the supported? check.
    assert not asserts_claim("the CEO resigned in March", response)


# --- 2-run averaging ----------------------------------------------------------

def test_combine_runs_resolves_flip_conservatively():
    run_a = [make_verdict("q1", 1), make_verdict("q2", 1)]
    run_b = [make_verdict("q1", 0), make_verdict("q2", 1)]  # q1 flipped
    combined = {v.question_id: v for v in combine_runs([run_a, run_b])}
    assert combined["q1"].score == 0          # flip resolved to 0
    assert "unstable" in combined["q1"].explanation
    assert combined["q2"].score == 1          # stable agreement preserved
