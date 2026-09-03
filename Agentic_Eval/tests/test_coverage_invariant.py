"""R4: coverage invariant — every active dimension is reported; no-data dims abstain; gates stay live."""

from __future__ import annotations

from aah.config import default_weight_config
from aah.contracts import Dimension
from aah.layer_a.aggregator import aggregate
from tests.conftest import make_question, make_verdict


def test_all_active_dimensions_appear_even_with_a_sparse_rubric():
    # Rubric touches ONE dimension; the record must still cover every active dimension.
    cfg = default_weight_config()
    rubric = [make_question("r1", Dimension.RELEVANCE)]
    score = aggregate([make_verdict("r1", 1)], rubric, cfg)
    reported = {d.dimension for d in score.per_dimension}
    assert reported == set(cfg.tiers)  # nothing skipped


def test_dimensions_with_no_data_abstain():
    rubric = [make_question("r1", Dimension.RELEVANCE)]
    score = aggregate([make_verdict("r1", 1)], rubric, default_weight_config())
    rel = next(d for d in score.per_dimension if d.dimension is Dimension.RELEVANCE)
    other = next(d for d in score.per_dimension if d.dimension is Dimension.CLARITY)
    assert not rel.abstained and rel.weight > 0.0
    assert other.abstained and other.weight == 0.0  # no data -> abstains, no weight


def test_abstention_does_not_distort_overall():
    # A single relevance=1 with everything else abstaining -> overall 1.0, not dragged down by zeros.
    rubric = [make_question("r1", Dimension.RELEVANCE)]
    score = aggregate([make_verdict("r1", 1)], rubric, default_weight_config())
    assert score.overall == 1.0
    assert not score.failed


def test_gate_still_fires_amid_abstaining_dimensions():
    # A CRITICAL failure gates even though most dimensions abstain.
    rubric = [
        make_question("r1", Dimension.RELEVANCE),
        make_question("inj1", Dimension.INJECTION_RESISTANCE),
    ]
    verdicts = [make_verdict("r1", 1), make_verdict("inj1", 0)]
    score = aggregate(verdicts, rubric, default_weight_config())
    assert score.failed and score.gated_by is Dimension.INJECTION_RESISTANCE
    # the many abstaining dims are still present in the record
    assert any(d.abstained for d in score.per_dimension)
