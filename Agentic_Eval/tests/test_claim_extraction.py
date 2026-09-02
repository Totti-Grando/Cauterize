"""Tests for per-claim extraction + truthfulness binding (aah/api/claim_extraction.py).

Deterministic throughout — the stub extractor and overlap proxies need no model.
"""

from __future__ import annotations

import asyncio

import pytest

from aah.api.claim_extraction import (
    ClaimParent, ExtractedClaim, LlmClaimExtractor, StubClaimExtractor,
    _attribution, _citations, _coerce_claims, _loads_array, build_claim_nodes, extract_and_score,
)

_Q = "What drove Q3 results and what risks emerged?"
_R = (
    "Q3 revenue was $4.2 billion. Cloud gross margin improved to 68%. "
    "Therefore cloud is the primary growth driver. The mascot is a penguin."
)
_CTX = "Filing: Q3 revenue totaled $4.2 billion. Cloud gross margin rose to 68% from 61%."


def _run(coro):
    return asyncio.run(coro)


def test_stub_tags_anchored_derived_and_orphan():
    claims = _run(StubClaimExtractor().extract(_Q, _R, _CTX))
    by_text = {c.text: c for c in claims}
    rev = next(c for c in claims if "revenue" in c.text)
    drv = next(c for c in claims if "growth driver" in c.text)
    orph = next(c for c in claims if "penguin" in c.text)
    assert rev.kind == "anchored"
    assert drv.kind == "derived" and drv.parents            # a connective -> derived, with parents
    assert orph.kind == "orphan"                            # overlaps neither question nor context


def test_deterministic_grounding_is_overlap_against_context():
    tree = _run(extract_and_score(_Q, _R, _CTX))
    rev = next(n for n in tree.values() if "revenue" in n.text)
    # revenue claim's content words all appear in the filing context -> high groundedness
    assert rev.groundedness is not None and rev.groundedness >= 0.8
    assert rev.kind == "anchored" and rev.score == pytest.approx(rev.own_truthfulness)


def test_orphan_relevance_is_vs_question_not_the_answer():
    tree = _run(extract_and_score(_Q, _R, _CTX))
    orph = next(n for n in tree.values() if "penguin" in n.text)
    assert orph.kind == "orphan"
    # the mascot fact does not address the question -> low relevance (NOT ~1.0 vs its own sentence)
    assert orph.relevance is not None and orph.relevance < 0.3


def test_derived_node_gets_parents_and_reasoning_and_scores():
    tree = _run(extract_and_score(_Q, _R, _CTX))
    drv = next(n for n in tree.values() if "growth driver" in n.text)
    assert drv.kind == "derived"
    assert drv.parent_min is not None            # gate computed from parents
    assert drv.reasoning_fidelity is not None     # reasoning steps scored
    assert drv.score is not None


def test_injected_grounding_scorer_is_used():
    async def always_high(claim, response, context):
        return 0.95

    async def go():
        claims = await StubClaimExtractor().extract(_Q, _R, _CTX)
        return await build_claim_nodes(claims, response=_R, context=_CTX, question=_Q,
                                       grounded=always_high, attribution=always_high)

    tree = _run(go())
    anchored = [n for n in tree.values() if n.kind == "anchored"]
    # quality (from no evidence) is 0.75, grounding/attribution forced to 0.95 -> min = 0.75
    assert anchored and all(n.own_truthfulness == pytest.approx(0.75) for n in anchored)


def test_loads_array_extracts_json_even_with_prose_around_it():
    text = 'Sure, here it is:\n[{"id":"c0","text":"x","kind":"anchored"}]\nThanks.'
    arr = _loads_array(text)
    assert isinstance(arr, list) and arr[0]["id"] == "c0"
    assert _loads_array("no json here") == []


def test_coerce_claims_validates_kind_and_parents():
    data = [
        {"id": "c0", "text": "a", "kind": "anchored"},
        {"id": "c1", "text": "b", "kind": "bogus",                       # invalid kind -> anchored
         "parents": [{"id": "c0", "load_bearing": False, "or_group": "g"}], "reasoning_steps": ["s1"]},
    ]
    claims = _coerce_claims(data)
    assert claims[1].kind == "anchored"
    assert claims[1].parents[0] == ClaimParent("c0", False, "g")
    assert claims[1].reasoning_steps == ["s1"]


def test_llm_extractor_parses_injected_client_response():
    class _Msg:
        content = [type("B", (), {"type": "text", "text": '[{"id":"c0","text":"rev","kind":"anchored"}]'})()]

    class _Client:
        class messages:
            @staticmethod
            async def create(**kw):
                return _Msg()

    claims = _run(LlmClaimExtractor(client=_Client()).extract(_Q, _R, _CTX))
    assert len(claims) == 1 and claims[0].text == "rev" and claims[0].kind == "anchored"


def test_empty_answer_yields_empty_tree():
    tree = _run(extract_and_score(_Q, "", _CTX))
    assert tree == {}


# --- source attribution (citation validity) --------------------------------------------
_EVIDENCE = [{"title": "Q3 filing", "domain": "sec.gov"},
             {"title": "Newswire report", "domain": "newswire.example.com"}]


def test_citations_are_extracted():
    refs = _citations("Revenue rose, according to the Q3 filing, and per Newswire report.")
    joined = " ".join(refs).lower()
    assert "filing" in joined and "newswire" in joined
    assert _citations("Revenue simply rose this quarter.") == []      # no citation


def test_attribution_present_for_cited_in_set_source():
    assert _attribution("Revenue rose according to the Q3 filing", _EVIDENCE) == 1.0


def test_attribution_zero_for_fabricated_citation():
    # cites a source that is NOT in the provided evidence set -> fabricated -> 0.0
    assert _attribution("Profits doubled according to the Bloomberg terminal", _EVIDENCE) == 0.0


def test_attribution_none_when_no_citation_or_no_evidence():
    assert _attribution("Revenue rose this quarter", _EVIDENCE) is None       # nothing cited -> N/A
    assert _attribution("per the Q3 filing", []) is None                      # no source set -> N/A


def test_fabricated_citation_drags_claim_score_via_min():
    async def go():
        claims = [ExtractedClaim("c0", "Profits tripled according to the Bloomberg terminal", "anchored")]
        # grounding forced high so attribution is the deciding (weakest) factor
        async def high(*_a):
            return 0.95
        return await build_claim_nodes(claims, response="", context="", question="",
                                       evidence=_EVIDENCE, grounded=high)

    tree = _run(go())
    n = tree["c0"]
    assert n.source_attribution == 0.0
    assert n.own_truthfulness == 0.0            # min(grounded=0.95, attribution=0.0, quality) == 0.0
    assert n.score == 0.0
