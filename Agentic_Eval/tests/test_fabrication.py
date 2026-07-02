"""F3: source-fabrication is a deterministic gate — cited sources must be present in context."""

from __future__ import annotations

import asyncio

from aah.contracts import Dimension, EvalMethod, Mode
from aah.layer_a.rubric_norm import prepare_rubric
from aah.layer_a.scorers import FabricationScorer
from aah.layer_a.scorers.fabrication import unsupported_citations
from tests.conftest import make_question

_CONTEXT = (
    "Q3 briefing. See https://research.example.com/issuer/esg for the report. "
    'The memo states "revenue rose 8% year over year" in the summary.'
)


def _q():
    return make_question("f", Dimension.SOURCE_FABRICATION, eval_method=EvalMethod.SOURCE_CHECK)


def test_fabricated_url_fails_with_span_in_evidence():
    resp = "According to https://totally-made-up.example/fake-article, risk spiked."
    v = asyncio.run(FabricationScorer().score(_q(), resp, _CONTEXT))
    assert v.score == 0
    assert "totally-made-up.example" in v.evidence


def test_fabricated_quote_fails():
    resp = 'The source says "profit tripled overnight" which is alarming.'
    v = asyncio.run(FabricationScorer().score(_q(), resp, _CONTEXT))
    assert v.score == 0
    assert "profit tripled overnight" in v.evidence


def test_in_context_citation_passes():
    resp = "As reported at https://research.example.com/issuer/esg, the numbers hold."
    v = asyncio.run(FabricationScorer().score(_q(), resp, _CONTEXT))
    assert v.score == 1


def test_no_citations_passes():
    v = asyncio.run(FabricationScorer().score(_q(), "A general statement with no sources.", _CONTEXT))
    assert v.score == 1


def test_unsupported_citations_helper():
    resp = "see https://a.example/x and https://research.example.com/issuer/esg"
    missing = unsupported_citations(resp, _CONTEXT)
    assert missing == ["https://a.example/x"]  # only the out-of-context one


def test_fabrication_gate_routes_to_source_check_not_judge():
    # A SOURCE_FABRICATION check must be routed to the deterministic gate, never the LLM judge,
    # and must remain a CRITICAL gating dimension after normalization (not reclassified).
    q = make_question("g", Dimension.SOURCE_FABRICATION, eval_method=EvalMethod.LLM_JUDGE,
                      must_pass=True)
    (out,) = prepare_rubric([q], Mode.QUALITY)
    assert out.eval_method is EvalMethod.SOURCE_CHECK
    assert out.dimension is Dimension.SOURCE_FABRICATION
    assert out.must_pass is True
