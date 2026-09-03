"""F8: phi de-dup removes redundant near-duplicate checks before the uniform per-dimension mean."""

from __future__ import annotations

from aah.config import default_weight_config
from aah.contracts import Dimension, EvalMethod, Verdict
from aah.determinism_guards import kept_after_phi_dedup
from aah.layer_a.aggregator import aggregate
from tests.conftest import make_question

_AC = Dimension.ANSWER_CORRECTNESS


def test_phi_dedup_drops_identical_varying_check():
    dim_of = {"a": _AC, "b": _AC, "c": _AC}
    scores = {"a": [1, 0, 1, 0], "b": [1, 0, 1, 0], "c": [1, 1, 0, 0]}  # a==b (phi=1); c differs
    kept = kept_after_phi_dedup(dim_of, scores, phi_threshold=0.9)
    assert kept == {"a", "c"}  # the duplicate b is dropped, counted once


def test_no_dedup_without_variance():
    dim_of = {"a": _AC, "b": _AC}
    scores = {"a": [1, 1], "b": [1, 1]}  # constant vectors → phi 0 → nothing dropped
    assert kept_after_phi_dedup(dim_of, scores) == {"a", "b"}


def test_dedup_only_within_a_dimension():
    dim_of = {"a": _AC, "b": Dimension.RELEVANCE}
    scores = {"a": [1, 0, 1, 0], "b": [1, 0, 1, 0]}  # identical but different dims → both kept
    assert kept_after_phi_dedup(dim_of, scores) == {"a", "b"}


def test_dropping_duplicate_changes_the_dimension_mean():
    a = make_question("a", _AC, eval_method=EvalMethod.DETERMINISTIC)
    b = make_question("b", _AC, eval_method=EvalMethod.DETERMINISTIC)
    c = make_question("c", _AC, eval_method=EvalMethod.DETERMINISTIC)
    verdicts = [
        Verdict(question_id="a", score=1, explanation="x"),
        Verdict(question_id="b", score=1, explanation="x"),  # duplicate of a
        Verdict(question_id="c", score=0, explanation="x"),
    ]
    cfg = default_weight_config()

    def ac_score(run):
        return next(d.score for d in run.per_dimension if d.dimension is _AC)

    with_dupe = aggregate(verdicts, [a, b, c], cfg)             # mean 2/3 (a,b double-weight the pass)
    deduped = aggregate(verdicts, [a, b, c], cfg, {"a", "c"})   # mean 1/2 (b dropped)
    assert ac_score(with_dupe) != ac_score(deduped)
    assert abs(ac_score(deduped) - 0.5) < 1e-9
