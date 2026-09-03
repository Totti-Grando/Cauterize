"""R1/R2: taxonomy registration + per-dimension scorer routing."""

from __future__ import annotations

import pytest

from aah.config.policy import POLICY_TABLE
from aah.config.taxonomy import (
    DIMENSION_EVAL_METHOD,
    DIMENSION_META,
    DIMENSIONS_BY_CATEGORY,
    TAXONOMY_DIMENSIONS,
)
from aah.contracts import Category, Dimension, EvalMethod, Tier
from aah.layer_a.router import RealEvaluatorRouter, default_router


# --- R1: registration -------------------------------------------------------------
def test_every_dimension_registered_with_category_and_tier():
    for dim in Dimension:
        assert dim in DIMENSION_META, f"{dim} missing from DIMENSION_META"
        assert dim in POLICY_TABLE, f"{dim} missing a tier"
        assert isinstance(POLICY_TABLE[dim], Tier)


def test_taxonomy_has_35_dimensions_across_10_categories():
    assert len(TAXONOMY_DIMENSIONS) == 35
    assert len(DIMENSIONS_BY_CATEGORY) == 10
    assert sum(len(v) for v in DIMENSIONS_BY_CATEGORY.values()) == 35


def test_taxonomy_names_are_unique():
    names = [m.taxonomy_name for m in DIMENSION_META.values()]
    assert len(names) == len(set(names))


def test_agentic_dims_have_no_category():
    for dim in (Dimension.UNSAFE_TOOL_USE, Dimension.UNBOUNDED_CONSUMPTION):
        assert DIMENSION_META[dim].category is None
        assert dim not in TAXONOMY_DIMENSIONS


def test_gating_subtypes_registered_per_section_1():
    # accuracy gates via fabrication; hallucination via fabricated_source/invented_policy; etc.
    from aah.contracts import Subtype

    assert Subtype.FABRICATION in DIMENSION_META[Dimension.ANSWER_CORRECTNESS].gating_subtypes
    assert Subtype.FABRICATED_SOURCE in DIMENSION_META[Dimension.SOURCE_FABRICATION].gating_subtypes
    assert Subtype.INVENTED_POLICY in DIMENSION_META[Dimension.SOURCE_FABRICATION].gating_subtypes
    assert Subtype.CONSTRAINT_VIOLATION in DIMENSION_META[Dimension.REGULATORY_COMPLIANCE].gating_subtypes
    assert Subtype.INSECURE_ADVICE in DIMENSION_META[Dimension.SECURITY_COMPLIANCE].gating_subtypes


# --- R2: routing ------------------------------------------------------------------
def test_every_dimension_has_an_eval_method():
    for dim in Dimension:
        assert dim in DIMENSION_EVAL_METHOD
        assert isinstance(DIMENSION_EVAL_METHOD[dim], EvalMethod)


def test_default_router_covers_every_dimension():
    # Builds the full router and runs the load-time coverage assertion.
    default_router(client=object()).assert_covers_taxonomy()


def test_router_missing_scorer_raises_at_load():
    incomplete = RealEvaluatorRouter({EvalMethod.DETERMINISTIC: object()})
    with pytest.raises(KeyError):
        incomplete.assert_covers_taxonomy()
