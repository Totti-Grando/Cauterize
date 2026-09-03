"""Tests for the claim-graph builder (aah/api/claim_graph.py).

The builder is a pure transform over the UI ``evaluation`` dict, so these tests are fully offline:
they feed synthetic and real-fixture evaluation dicts and assert the graph's structure, the
orphan/AND classification, the layout, and the standalone HTML render.
"""

from __future__ import annotations

import asyncio

import pytest

from aah.api import claim_graph as cg
from aah.api.offline_fixtures import case_meta, run_scenario
from aah.api.ui_adapter import audit_to_evaluation


def _eval(**over) -> dict:
    """A minimal but complete evaluation dict; override any field."""
    base = {
        "id": "E-TST", "questionId": "Q-TST", "question": "Is the answer grounded?",
        "provider": "test", "verdict": "partial", "overall": 0.5, "gatedBy": None,
        "evidence": [], "perDimension": [], "rubric": [],
    }
    base.update(over)
    return base


def test_empty_evaluations_are_valid_and_empty():
    payload = cg.build_graph([])
    assert payload["summary"]["evaluations"] == 0
    assert payload["graphs"] == []
    # single empty evaluation still builds a lone question node
    g = cg.build_evaluation_graph(_eval(rubric=[]))
    assert g["stats"]["nodes"] == 1  # just the question root
    assert g["stats"]["edges"] == 0


def test_must_pass_check_is_a_gate_with_and_edges():
    ev = _eval(
        gatedBy="factual_consistency",
        perDimension=[{"dimension": "factual_consistency", "tier": "major", "gating": False, "score": 0.0, "weight": 2.0}],
        rubric=[{"requirement": "Do not overclaim", "checks": [
            {"id": "c0", "text": "no unsupported materiality", "dimension": "factual_consistency",
             "tier": "major", "eval_method": "deterministic", "must_pass": True, "score": 0, "reason": "overclaimed"},
        ]}],
    )
    g = cg.build_evaluation_graph(ev)
    gate_nodes = [n for n in g["nodes"] if n.get("gate")]
    assert len(gate_nodes) == 1 and gate_nodes[0]["must_pass"] is True
    # a gate produces BOTH a hard "decomposes(and)" edge and a "gates" edge to the root
    kinds = {(e["kind"], e.get("relation")) for e in g["edges"]}
    assert ("decomposes", "and") in kinds
    assert any(e["kind"] == "gates" and e.get("failed") for e in g["edges"])
    assert g["stats"]["gates"] == 1 and g["stats"]["and_edges"] >= 1


def test_ordinary_check_is_a_soft_relation():
    ev = _eval(rubric=[{"requirement": "R", "checks": [
        {"id": "c0", "text": "states a trend", "dimension": "answer_correctness",
         "tier": "major", "eval_method": "deterministic", "must_pass": False, "score": 1, "reason": "ok"},
    ]}])
    g = cg.build_evaluation_graph(ev)
    assert g["stats"]["gates"] == 0
    assert any(e["kind"] == "decomposes" and e.get("relation") == "soft" for e in g["edges"])


def test_unsupported_claim_is_an_orphan():
    ev = _eval(
        evidence=[{"id": "s1", "title": "Doc", "domain": "x.com", "support": "strong", "fetchSuccess": True}],
        rubric=[{"requirement": "Ground it", "checks": [
            {"id": "c0", "text": "claim entailed by source", "dimension": "factual_consistency",
             "tier": "major", "eval_method": "nli", "must_pass": False, "score": 0, "reason": "not entailed"},
        ]}],
    )
    g = cg.build_evaluation_graph(ev)
    claim = next(n for n in g["nodes"] if n["type"] == "claim")
    assert claim["orphan"] is True and "unsupported" in claim["orphan_reason"]
    # a failing claim draws NO grounds edge
    assert not any(e["kind"] == "grounds" for e in g["edges"])


def test_passing_claim_grounds_to_supporting_source():
    ev = _eval(
        evidence=[{"id": "s1", "title": "Doc", "domain": "x.com", "support": "strong", "fetchSuccess": True}],
        rubric=[{"requirement": "Ground it", "checks": [
            {"id": "c0", "text": "claim entailed by source", "dimension": "factual_consistency",
             "tier": "major", "eval_method": "nli", "must_pass": False, "score": 1, "reason": "entailed"},
        ]}],
    )
    g = cg.build_evaluation_graph(ev)
    assert any(e["kind"] == "grounds" for e in g["edges"])
    src = next(n for n in g["nodes"] if n["type"] == "source")
    assert not src.get("orphan")  # it grounds a claim, so not an orphan


def test_failed_fetch_source_is_an_orphan():
    ev = _eval(evidence=[{"id": "s1", "title": "Portal", "domain": "x.com", "support": "not_evaluable", "fetchSuccess": False}])
    g = cg.build_evaluation_graph(ev)
    src = next(n for n in g["nodes"] if n["type"] == "source")
    assert src["orphan"] is True and "retriev" in src["orphan_reason"]


def test_check_without_requirement_marks_orphan_requirement():
    ev = _eval(rubric=[{"requirement": "(unspecified requirement)", "checks": [
        {"id": "c0", "text": "holistic", "dimension": "relevance", "tier": "major",
         "eval_method": "llm_judge", "must_pass": False, "score": None, "reason": ""},
    ]}])
    g = cg.build_evaluation_graph(ev)
    req = next(n for n in g["nodes"] if n["type"] == "requirement")
    assert req["orphan"] is True
    # an orphan requirement is not wired to the question root
    assert not any(e["kind"] == "has" and e["target"] == req["id"] for e in g["edges"])


def test_layout_positions_every_node_and_bands_orphans_lower():
    ev = _eval(
        evidence=[{"id": "s1", "title": "Portal", "support": "not_evaluable", "fetchSuccess": False},
                  {"id": "s2", "title": "Good", "support": "strong", "fetchSuccess": True}],
        rubric=[{"requirement": "R", "checks": [
            {"id": "c0", "text": "grounded", "dimension": "factual_consistency", "tier": "major",
             "eval_method": "nli", "must_pass": False, "score": 1, "reason": "ok"},
        ]}],
    )
    g = cg.build_evaluation_graph(ev)
    assert all("x" in n and "y" in n for n in g["nodes"])
    sources = [n for n in g["nodes"] if n["type"] == "source"]
    orphan = next(n for n in sources if n.get("orphan"))
    healthy = next(n for n in sources if not n.get("orphan"))
    # orphan sources sit below healthy ones in the same column
    assert orphan["x"] == healthy["x"] and orphan["y"] > healthy["y"]


def test_claim_classification_is_category_driven_not_hardcoded():
    # a check in an evidence/RAG category is a grounding CLAIM even when its dimension NAME is unknown
    # to the graph — classification follows the config-carried category, not a frozen name list.
    ev = _eval(rubric=[{"requirement": "R", "checks": [
        {"id": "c0", "text": "novel rag dim", "dimension": "some_future_rag_dim",
         "category": "rag_quality", "tier": "major", "score": 1, "reason": "ok"},
        {"id": "c1", "text": "a quality check", "dimension": "answer_correctness",
         "category": "response_quality", "tier": "major", "score": 1, "reason": "ok"},
    ]}])
    g = cg.build_evaluation_graph(ev)
    by_dim = {n.get("dimension"): n["type"] for n in g["nodes"] if n["type"] in ("claim", "check")}
    assert by_dim["some_future_rag_dim"] == "claim"       # rag_quality category -> claim
    assert by_dim["answer_correctness"] == "check"        # response_quality category -> plain check


def test_legacy_record_without_category_falls_back_to_dim_names():
    # a record predating the category field still classifies via the fallback dimension set
    ev = _eval(rubric=[{"requirement": "R", "checks": [
        {"id": "c0", "text": "grounded", "dimension": "factual_consistency",
         "tier": "major", "score": 1, "reason": "ok"},          # no 'category' key
    ]}])
    g = cg.build_evaluation_graph(ev)
    assert next(n for n in g["nodes"] if n["id"].endswith("c:c0"))["type"] == "claim"


def test_subtype_gated_check_is_an_and_gate():
    # a scored (MAJOR, non-must-pass) check whose failure subtype gates the run — from the run config,
    # NOT a critical tier or must_pass — must still be rendered as an AND gate.
    ev = _eval(
        perDimension=[{"dimension": "source_fabrication", "tier": "major", "gating": False,
                       "category": "evidence_truthfulness", "score": 0.0, "weight": 2.0}],
        rubric=[{"requirement": "No fabricated sources", "checks": [
            {"id": "c0", "text": "cited source exists", "dimension": "source_fabrication",
             "category": "evidence_truthfulness", "subtype": "fabricated_source", "tier": "major",
             "must_pass": False, "subtype_gates": True, "score": 0, "reason": "fabricated"},
        ]}])
    g = cg.build_evaluation_graph(ev)
    gate = next(n for n in g["nodes"] if n.get("gate"))
    assert gate["subtype_gates"] is True and gate["must_pass"] is False and gate["tier"] == "major"
    assert any(e["kind"] == "gates" and e.get("failed") for e in g["edges"])


def test_adapter_carries_category_and_subtype_from_config():
    # the whole point: the graph's config comes from the adapter, so the adapter must emit category +
    # subtype + subtype_gates on real fixtures.
    pairs = asyncio.run(run_scenario())
    evals = [audit_to_evaluation(rec, case_meta(case, "test")) for case, rec in pairs]
    dims = [d for ev in evals for d in ev["perDimension"]]
    checks = [c for ev in evals for grp in ev["rubric"] for c in grp["checks"]]
    assert dims and all("category" in d for d in dims)
    assert checks and all("category" in c and "subtype" in c and "subtype_gates" in c for c in checks)


def test_all_configured_dimensions_render_even_when_no_check_touches_them():
    # the graph must show the FULL evaluation configuration, not only dimensions a check exercised
    ev = _eval(
        perDimension=[
            {"dimension": "factual_consistency", "category": "evidence_truthfulness",
             "tier": "major", "gating": False, "score": 0.5, "weight": 2.0},
            {"dimension": "toxicity", "category": "safety", "tier": "major", "gating": False,
             "score": 1.0, "weight": 1.0},
            {"dimension": "clarity", "category": "communication", "tier": "minor", "gating": False,
             "score": 0.8, "weight": 1.0},
        ],
        rubric=[{"requirement": "R", "checks": [
            {"id": "c0", "text": "grounded", "dimension": "factual_consistency",
             "category": "evidence_truthfulness", "tier": "major", "score": 1, "reason": "ok"},
        ]}])
    g = cg.build_evaluation_graph(ev)
    dims = {n["dimension"] for n in g["nodes"] if n["type"] == "dimension"}
    assert dims == {"factual_consistency", "toxicity", "clarity"}        # all 3 configured dims appear
    # the dimension a check scored is 'exercised'; the untouched ones are not
    by_dim = {n["dimension"]: n for n in g["nodes"] if n["type"] == "dimension"}
    assert by_dim["factual_consistency"]["exercised"] is True
    assert by_dim["toxicity"]["exercised"] is False and by_dim["clarity"]["exercised"] is False


def test_dimension_lane_is_banded_by_category():
    ev = _eval(perDimension=[
        {"dimension": "clarity", "category": "communication", "tier": "minor", "score": 1, "weight": 1},
        {"dimension": "factual_consistency", "category": "evidence_truthfulness", "tier": "major", "score": 1, "weight": 1},
        {"dimension": "structure", "category": "communication", "tier": "minor", "score": 1, "weight": 1},
        {"dimension": "source_quality", "category": "evidence_truthfulness", "tier": "major", "score": 1, "weight": 1},
    ])
    g = cg.build_evaluation_graph(ev)
    dim_nodes = sorted([n for n in g["nodes"] if n["type"] == "dimension"], key=lambda n: n["y"])
    cats = [n["category"] for n in dim_nodes]
    # each category is contiguous (no category split across two bands)
    transitions = sum(1 for a, b in zip(cats, cats[1:]) if a != b)
    assert transitions == len(set(cats)) - 1
    assert len(dim_nodes) == 4


def test_render_html_is_self_contained_and_filled():
    payload = cg.build_graph([_eval()])
    html = cg.render_html(payload, title="X")
    assert html.startswith("<!doctype html>")
    assert "__PAYLOAD__" not in html and "__TITLE__" not in html
    assert '"graphs"' in html  # data embedded
    assert "http://" not in html.split("PAYLOAD")[0]  # no external asset before data


def test_builds_on_real_offline_fixtures():
    pairs = asyncio.run(run_scenario())
    evals = [audit_to_evaluation(rec, case_meta(case, "test")) for case, rec in pairs]
    payload = cg.build_graph(evals, source="fixtures")
    assert payload["summary"]["evaluations"] == 5
    # the fixtures are hand-built to include a gate (Q-004 must-pass) and orphans (failed fetch,
    # unsupported claims) — the whole point of the demo — so the graph must surface them.
    assert payload["summary"]["gates"] >= 1
    assert payload["summary"]["orphans"] >= 2
