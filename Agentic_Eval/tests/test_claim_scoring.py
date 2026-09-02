"""Tests for the nodal claim-scoring rollup (aah/api/claim_scoring.py).

Each test pins one branch of the locked scoring model so the arithmetic can't silently drift.
"""

from __future__ import annotations

import pytest

from aah.api.claim_scoring import (
    AXIOM_THRESHOLD, ClaimNode, ParentLink, band, score_tree, to_graph,
)


def _tree(*nodes: ClaimNode) -> dict[str, ClaimNode]:
    return score_tree({n.id: n for n in nodes})


def test_anchored_is_weakest_link_min_of_three():
    t = _tree(ClaimNode(id="a", text="anchored", kind="anchored",
                        groundedness=0.9, source_attribution=0.8, source_quality=0.7))
    assert t["a"].score == pytest.approx(0.7)
    assert t["a"].branch == "anchored:min(3)"


def test_derived_above_axiom_takes_max_of_own_and_reasoning():
    # parent is axiom-grade (>=0.75), so good reasoning can exceed thin own grounding
    t = _tree(
        ClaimNode(id="p", text="premise", kind="anchored", groundedness=0.8, source_attribution=0.8, source_quality=0.8),
        ClaimNode(id="d", text="derived", kind="derived", groundedness=0.6, source_attribution=0.6,
                  source_quality=0.6, reasoning_fidelity=0.9, parents=[ParentLink("p")]),
    )
    assert t["d"].parent_min == pytest.approx(0.8)
    assert t["d"].score == pytest.approx(0.9)          # max(own=0.6, rf=0.9)
    assert "max(own,rf)" in t["d"].branch


def test_derived_below_axiom_takes_min_of_own_and_reasoning():
    # weak premise -> reasoning is meaningless -> min pulls it down
    t = _tree(
        ClaimNode(id="p", text="weak premise", kind="anchored", groundedness=0.5, source_attribution=0.5, source_quality=0.5),
        ClaimNode(id="d", text="derived", kind="derived", groundedness=0.6, source_attribution=0.6,
                  source_quality=0.6, reasoning_fidelity=0.9, parents=[ParentLink("p")]),
    )
    assert t["d"].parent_min == pytest.approx(0.5)
    assert t["d"].score == pytest.approx(0.6)          # min(own=0.6, rf=0.9)
    assert "min(own,rf)" in t["d"].branch


def test_axiom_threshold_boundary_is_inclusive():
    t = _tree(
        ClaimNode(id="p", text="p", kind="anchored", groundedness=AXIOM_THRESHOLD,
                  source_attribution=AXIOM_THRESHOLD, source_quality=AXIOM_THRESHOLD),
        ClaimNode(id="d", text="d", kind="derived", groundedness=0.6, source_attribution=0.6,
                  source_quality=0.6, reasoning_fidelity=0.9, parents=[ParentLink("p")]),
    )
    assert t["d"].parent_min == pytest.approx(AXIOM_THRESHOLD)
    assert t["d"].score == pytest.approx(0.9)          # >= threshold -> max branch


def test_or_group_reduced_by_max_so_weak_alternative_does_not_drag_gate():
    # p_hi OR p_lo are alternatives; the group contributes max(0.9, 0.3)=0.9. A separate AND parent
    # c=0.8. So m = min(0.9, 0.8) = 0.8 -> axiom, NOT dragged to 0.3 by the weak OR alternative.
    t = _tree(
        ClaimNode(id="p_hi", text="alt A", kind="anchored", groundedness=0.9, source_attribution=0.9, source_quality=0.9),
        ClaimNode(id="p_lo", text="alt B", kind="anchored", groundedness=0.3, source_attribution=0.3, source_quality=0.3),
        ClaimNode(id="c", text="required", kind="anchored", groundedness=0.8, source_attribution=0.8, source_quality=0.8),
        ClaimNode(id="d", text="derived", kind="derived", groundedness=0.6, source_attribution=0.6, source_quality=0.6,
                  reasoning_fidelity=0.95,
                  parents=[ParentLink("p_hi", or_group="g1"), ParentLink("p_lo", or_group="g1"), ParentLink("c")]),
    )
    assert t["d"].parent_min == pytest.approx(0.8)
    assert t["d"].score == pytest.approx(0.95)         # axiom -> max(0.6, 0.95)


def test_non_load_bearing_parent_is_excluded_from_gate():
    # a decorative parent at 0.1 must NOT lower the gate below the load-bearing parent's 0.8
    t = _tree(
        ClaimNode(id="lb", text="load bearing", kind="anchored", groundedness=0.8, source_attribution=0.8, source_quality=0.8),
        ClaimNode(id="deco", text="decorative", kind="anchored", groundedness=0.1, source_attribution=0.1, source_quality=0.1),
        ClaimNode(id="d", text="derived", kind="derived", groundedness=0.6, source_attribution=0.6, source_quality=0.6,
                  reasoning_fidelity=0.9,
                  parents=[ParentLink("lb"), ParentLink("deco", load_bearing=False)]),
    )
    assert t["d"].parent_min == pytest.approx(0.8)     # deco's 0.1 excluded
    assert t["d"].score == pytest.approx(0.9)


def test_derived_with_no_reasoning_falls_back_to_own_truthfulness():
    t = _tree(
        ClaimNode(id="p", text="p", kind="anchored", groundedness=0.9, source_attribution=0.9, source_quality=0.9),
        ClaimNode(id="d", text="d", kind="derived", groundedness=0.7, source_attribution=0.7, source_quality=0.7,
                  reasoning_fidelity=None, parents=[ParentLink("p")]),
    )
    assert t["d"].score == pytest.approx(0.7)          # only own present -> own


def test_orphan_scores_on_relevance_stub():
    t = _tree(ClaimNode(id="o", text="floating fact", kind="orphan", relevance=0.4))
    assert t["o"].score == pytest.approx(0.4)
    assert t["o"].branch == "orphan:relevance"


def test_recursive_chain_anchored_to_derived_to_derived():
    t = _tree(
        ClaimNode(id="a", text="leaf", kind="anchored", groundedness=0.9, source_attribution=0.9, source_quality=0.9),
        ClaimNode(id="d1", text="mid", kind="derived", groundedness=0.8, source_attribution=0.8, source_quality=0.8,
                  reasoning_fidelity=0.85, parents=[ParentLink("a")]),
        ClaimNode(id="d2", text="top", kind="derived", groundedness=0.5, source_attribution=0.5, source_quality=0.5,
                  reasoning_fidelity=0.95, parents=[ParentLink("d1")]),
    )
    # d1: m=0.9 axiom -> max(0.8, 0.85)=0.85 ; d2: m=d1=0.85 axiom -> max(0.5, 0.95)=0.95
    assert t["d1"].score == pytest.approx(0.85)
    assert t["d2"].score == pytest.approx(0.95)


def test_cycle_is_broken_safely_and_terminates():
    # a<->b mutual dependency must not hang or raise
    t = _tree(
        ClaimNode(id="a", text="a", kind="derived", groundedness=0.8, source_attribution=0.8, source_quality=0.8,
                  reasoning_fidelity=0.6, parents=[ParentLink("b")]),
        ClaimNode(id="b", text="b", kind="derived", groundedness=0.7, source_attribution=0.7, source_quality=0.7,
                  reasoning_fidelity=0.6, parents=[ParentLink("a")]),
    )
    assert t["a"].score is not None and t["b"].score is not None


def test_to_graph_shape_and_bands():
    t = _tree(
        ClaimNode(id="a", text="leaf", kind="anchored", groundedness=0.9, source_attribution=0.9, source_quality=0.9),
        ClaimNode(id="d", text="top", kind="derived", groundedness=0.6, source_attribution=0.6, source_quality=0.6,
                  reasoning_fidelity=0.95, parents=[ParentLink("a")]),
    )
    g = to_graph(t, source="unit")
    assert g["stats"]["nodes"] == 2 and g["stats"]["edges"] == 1
    assert g["stats"]["anchored"] == 1 and g["stats"]["derived"] == 1
    a = next(n for n in g["nodes"] if n["id"] == "a")
    assert a["own_truthfulness"] == pytest.approx(0.9) and a["band"] == "green"
    e = g["edges"][0]
    assert e["source"] == "a" and e["target"] == "d" and e["relation"] == "and"


def test_band_thresholds():
    assert band(0.9) == "green" and band(0.6) == "amber" and band(0.2) == "red" and band(None) == "abstain"
