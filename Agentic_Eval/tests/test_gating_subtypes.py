"""R3: a scored MAJOR dimension vetoes the run on a triggered gating subtype, but only lowers
its score on a non-gating-subtype miss."""

from __future__ import annotations

import math

from aah.config import default_weight_config
from aah.contracts import Dimension, Subtype
from aah.layer_a.aggregator import aggregate
from tests.conftest import make_question, make_verdict


def test_hallucination_is_major_but_gates_on_fabricated_source():
    # SOURCE_FABRICATION maps to `hallucination` — MAJOR overall, gates on fabricated_source.
    assert default_weight_config().tiers[Dimension.SOURCE_FABRICATION].value == "major"
    rubric = [
        make_question("h1", Dimension.SOURCE_FABRICATION, subtype=Subtype.FABRICATED_SOURCE),
        make_question("rel1", Dimension.RELEVANCE),
    ]
    verdicts = [make_verdict("h1", 0), make_verdict("rel1", 1)]  # fabricated source failure
    score = aggregate(verdicts, rubric, default_weight_config())
    assert score.failed
    assert score.gated_by is Dimension.SOURCE_FABRICATION
    assert score.overall == 0.0


def test_same_dimension_non_gating_subtype_only_lowers_score():
    # A hallucination-dimension miss that is NOT a gating subtype (generic OTHER) must not gate.
    rubric = [
        make_question("h1", Dimension.SOURCE_FABRICATION, subtype=Subtype.OTHER),
        make_question("h2", Dimension.SOURCE_FABRICATION, subtype=Subtype.OTHER),
        make_question("rel1", Dimension.RELEVANCE),
    ]
    verdicts = [make_verdict("h1", 0), make_verdict("h2", 1), make_verdict("rel1", 1)]
    score = aggregate(verdicts, rubric, default_weight_config())
    assert not score.failed
    assert score.gated_by is None
    # hallucination dim scores 0.5 rather than gating.
    hall = next(d for d in score.per_dimension if d.dimension is Dimension.SOURCE_FABRICATION)
    assert math.isclose(hall.score, 0.5, abs_tol=1e-9)


def test_constraint_and_security_compliance_gate_on_their_subtypes():
    for dim, subtype in (
        (Dimension.REGULATORY_COMPLIANCE, Subtype.CONSTRAINT_VIOLATION),
        (Dimension.SECURITY_COMPLIANCE, Subtype.INSECURE_ADVICE),
    ):
        rubric = [make_question("q1", dim, subtype=subtype), make_question("rel1", Dimension.RELEVANCE)]
        verdicts = [make_verdict("q1", 0), make_verdict("rel1", 1)]
        score = aggregate(verdicts, rubric, default_weight_config())
        assert score.failed and score.gated_by is dim, dim
