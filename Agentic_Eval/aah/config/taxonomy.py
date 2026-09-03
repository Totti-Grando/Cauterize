"""The taxonomy registry (taxonomy §1) — category, taxonomy name, and gating subtype per dimension.

This is the structural half of the dimension policy: ``policy.py`` owns the *tier* (severity /
gating / base weight), this module owns the *category* (grouping for focus + reporting), the
*taxonomy name* (the §1 label an existing frozen ``Dimension`` value maps to), and the *gating
subtypes* (specific failures on which an otherwise-scored MAJOR dimension still vetoes the run).

The 16 original ``Dimension`` members are MAPPED here to their §1 names rather than renamed, so
every historical ``AuditRecord`` value still resolves. ``UNSAFE_TOOL_USE`` and
``UNBOUNDED_CONSUMPTION`` have no §1 home; they are retained as agentic-only dimensions
(``category=None``) and excluded from ``TAXONOMY_DIMENSIONS``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ..contracts import Category, Dimension, EvalMethod, Subtype


@dataclass(frozen=True)
class DimensionMeta:
    """Structural metadata for one dimension (tier lives in ``policy.POLICY_TABLE``)."""

    taxonomy_name: str
    category: Optional[Category]                       # None => agentic-only, outside the §1 taxonomy
    gating_subtypes: frozenset[Subtype] = field(default_factory=frozenset)
    note: str = ""


# Shorthand for the categories.
_RQ = Category.RESPONSE_QUALITY
_ET = Category.EVIDENCE_TRUTHFULNESS
_RE = Category.REASONING
_IF = Category.INSTRUCTION_FOLLOWING
_CO = Category.COMMUNICATION
_SA = Category.SAFETY
_FA = Category.FAIRNESS
_PS = Category.PRIVACY_SECURITY
_RO = Category.ROBUSTNESS
_RG = Category.RAG_QUALITY

DIMENSION_META: dict[Dimension, DimensionMeta] = {
    # --- Response Quality ---
    Dimension.ANSWER_CORRECTNESS: DimensionMeta(
        "accuracy", _RQ, frozenset({Subtype.FABRICATION}),
        "a materially false factual claim may gate via fabrication",
    ),
    Dimension.COMPLETENESS: DimensionMeta(
        "completeness", _RQ, note="CI-measured; abstains below min sample",
    ),
    Dimension.RELEVANCE: DimensionMeta("relevance", _RQ, note="holistic — capped at ~3 checks"),
    Dimension.TASK_SUCCESS: DimensionMeta("task_success", _RQ),
    # --- Evidence & Truthfulness ---
    Dimension.FACTUAL_CONSISTENCY: DimensionMeta("groundedness", _ET),
    Dimension.SOURCE_FABRICATION: DimensionMeta(
        "hallucination", _ET, frozenset({Subtype.FABRICATED_SOURCE, Subtype.INVENTED_POLICY}),
        "fabricated source / invented policy → CRITICAL gate",
    ),
    Dimension.SOURCE_QUALITY: DimensionMeta(
        "source_quality", _ET, note="re-tier to CRITICAL for high-stakes advice",
    ),
    Dimension.SOURCE_ATTRIBUTION: DimensionMeta("source_attribution", _ET),
    # --- Reasoning ---
    Dimension.EXPLAINABILITY: DimensionMeta("logical_consistency", _RE),
    Dimension.ASSUMPTION_QUALITY: DimensionMeta(
        "assumption_quality", _RE, note="MAJOR when an assumption drives a decision",
    ),
    Dimension.ABSTENTION_CALIBRATION: DimensionMeta(
        "uncertainty_handling", _RE, note="overconfidence on thin evidence is the failure",
    ),
    # --- Instruction Following ---
    Dimension.INSTRUCTION_FOLLOWING: DimensionMeta(
        "format_compliance", _IF, note="hard machine-format (JSON) → must_pass gate",
    ),
    Dimension.REGULATORY_COMPLIANCE: DimensionMeta(
        "constraint_compliance", _IF, frozenset({Subtype.CONSTRAINT_VIOLATION}),
        "violating a safety/legal restriction → CRITICAL gate",
    ),
    Dimension.PERSONA_COMPLIANCE: DimensionMeta("persona_compliance", _IF),
    # --- Communication ---
    Dimension.CLARITY: DimensionMeta("clarity", _CO),
    Dimension.STRUCTURE: DimensionMeta("structure", _CO),
    Dimension.CONCISENESS: DimensionMeta("conciseness", _CO),
    Dimension.ACTIONABILITY: DimensionMeta(
        "actionability", _CO, note="MAJOR for task-oriented assistants",
    ),
    # --- Safety ---
    Dimension.HARM: DimensionMeta("harmfulness", _SA, note="unsafe financial/legal/medical advice"),
    Dimension.TOXICITY: DimensionMeta("toxicity", _SA, note="zero-tolerance hateful/abusive output"),
    Dimension.REFUSAL_QUALITY: DimensionMeta(
        "refusal_quality", _SA, note="complying with a dangerous request fails",
    ),
    # --- Fairness ---
    Dimension.SAFETY_FAIRNESS: DimensionMeta(
        "bias", _FA, note="CRITICAL in lending/eligibility contexts",
    ),
    Dimension.STEREOTYPING: DimensionMeta("stereotyping", _FA),
    # --- Privacy & Security ---
    Dimension.PII_LEAKAGE: DimensionMeta("pii_leakage", _PS),
    Dimension.DATA_LEAKAGE: DimensionMeta("confidential_data_exposure", _PS),
    Dimension.PROMPT_LEAKAGE: DimensionMeta("prompt_leakage", _PS, note="system-prompt disclosure"),
    Dimension.SECURITY_COMPLIANCE: DimensionMeta(
        "security_compliance", _PS, frozenset({Subtype.INSECURE_ADVICE}),
        "actively insecure advice (plaintext creds) → CRITICAL gate",
    ),
    # --- Robustness ---
    Dimension.INJECTION_RESISTANCE: DimensionMeta(
        "prompt_injection_resistance", _RO, note="direct + indirect",
    ),
    Dimension.JAILBREAK_RESISTANCE: DimensionMeta("jailbreak_resistance", _RO),
    Dimension.ADVERSARIAL_ROBUSTNESS: DimensionMeta("adversarial_robustness", _RO),
    Dimension.ROBUSTNESS: DimensionMeta("paraphrase_stability", _RO),
    # --- RAG Quality ---
    Dimension.RETRIEVAL_PRECISION: DimensionMeta("retrieval_precision", _RG),
    Dimension.RETRIEVAL_RECALL: DimensionMeta(
        "retrieval_recall", _RG, note="missed critical chunk = omission",
    ),
    Dimension.CONTEXT_UTILIZATION: DimensionMeta(
        "context_utilization", _RG, note="good context retrieved but ignored",
    ),
    Dimension.CONTEXT_RELEVANCE: DimensionMeta("context_relevance", _RG),
    # --- agentic-only, retained (no §1 category) ---
    Dimension.UNSAFE_TOOL_USE: DimensionMeta(
        "unsafe_tool_use", None, note="[agentic only] excessive agency — outside §1 taxonomy",
    ),
    Dimension.UNBOUNDED_CONSUMPTION: DimensionMeta(
        "unbounded_consumption", None, note="[agentic only] cost/latency — outside §1 taxonomy",
    ),
}

#: The 35 §1 taxonomy dimensions (excludes the 2 retained agentic-only dimensions).
TAXONOMY_DIMENSIONS: frozenset[Dimension] = frozenset(
    d for d, m in DIMENSION_META.items() if m.category is not None
)

#: Dimensions grouped by category, in enum order (for focus resolution + reporting).
DIMENSIONS_BY_CATEGORY: dict[Category, list[Dimension]] = {
    cat: [d for d in Dimension if DIMENSION_META.get(d) and DIMENSION_META[d].category is cat]
    for cat in Category
}

#: Default cheapest-competent scorer per dimension (taxonomy §1 / R2). The generator uses this as
#: the routing hint and the router validates against it at load. Reasoning + Communication are
#: holistic -> ``llm_judge`` with dimension-specific prompts; leak/injection dims -> ``injection_detector``;
#: grounding -> ``nli``; source dims -> ``source_fetch``; hallucination -> ``source_check`` (F3).
#: RAG dims route to ``llm_judge`` on an INTERIM basis — dedicated retrieval-precision/recall
#: scorers do not exist yet and are a follow-up (see R2 note).
DIMENSION_EVAL_METHOD: dict[Dimension, EvalMethod] = {
    # Response Quality
    Dimension.ANSWER_CORRECTNESS: EvalMethod.LLM_JUDGE,
    Dimension.COMPLETENESS: EvalMethod.LLM_JUDGE,
    Dimension.RELEVANCE: EvalMethod.LLM_JUDGE,
    Dimension.TASK_SUCCESS: EvalMethod.LLM_JUDGE,
    # Evidence & Truthfulness
    Dimension.FACTUAL_CONSISTENCY: EvalMethod.NLI,           # groundedness
    Dimension.SOURCE_FABRICATION: EvalMethod.SOURCE_CHECK,   # hallucination (F3 fabrication gate)
    Dimension.SOURCE_QUALITY: EvalMethod.SOURCE_FETCH,
    Dimension.SOURCE_ATTRIBUTION: EvalMethod.SOURCE_FETCH,
    # Reasoning (holistic -> llm_judge)
    Dimension.EXPLAINABILITY: EvalMethod.LLM_JUDGE,          # logical_consistency
    Dimension.ASSUMPTION_QUALITY: EvalMethod.LLM_JUDGE,
    Dimension.ABSTENTION_CALIBRATION: EvalMethod.LLM_JUDGE,  # uncertainty_handling
    # Instruction Following
    Dimension.INSTRUCTION_FOLLOWING: EvalMethod.DETERMINISTIC,  # format_compliance (CHECK:json_valid ...)
    Dimension.REGULATORY_COMPLIANCE: EvalMethod.LLM_JUDGE,      # constraint_compliance
    Dimension.PERSONA_COMPLIANCE: EvalMethod.LLM_JUDGE,
    # Communication (holistic -> llm_judge)
    Dimension.CLARITY: EvalMethod.LLM_JUDGE,
    Dimension.STRUCTURE: EvalMethod.LLM_JUDGE,
    Dimension.CONCISENESS: EvalMethod.LLM_JUDGE,
    Dimension.ACTIONABILITY: EvalMethod.LLM_JUDGE,
    # Safety
    Dimension.HARM: EvalMethod.LLM_JUDGE,
    Dimension.TOXICITY: EvalMethod.LLM_JUDGE,
    Dimension.REFUSAL_QUALITY: EvalMethod.LLM_JUDGE,
    # Fairness
    Dimension.SAFETY_FAIRNESS: EvalMethod.LLM_JUDGE,         # bias
    Dimension.STEREOTYPING: EvalMethod.LLM_JUDGE,
    # Privacy & Security (leak dims -> injection_detector)
    Dimension.PII_LEAKAGE: EvalMethod.INJECTION_DETECTOR,
    Dimension.DATA_LEAKAGE: EvalMethod.INJECTION_DETECTOR,   # confidential_data_exposure
    Dimension.PROMPT_LEAKAGE: EvalMethod.INJECTION_DETECTOR,
    Dimension.SECURITY_COMPLIANCE: EvalMethod.LLM_JUDGE,
    # Robustness
    Dimension.INJECTION_RESISTANCE: EvalMethod.INJECTION_DETECTOR,  # prompt_injection_resistance
    Dimension.JAILBREAK_RESISTANCE: EvalMethod.INJECTION_DETECTOR,
    Dimension.ADVERSARIAL_ROBUSTNESS: EvalMethod.LLM_JUDGE,
    Dimension.ROBUSTNESS: EvalMethod.LLM_JUDGE,              # paraphrase_stability
    # RAG Quality (INTERIM llm_judge; dedicated retrieval scorers are a follow-up)
    Dimension.RETRIEVAL_PRECISION: EvalMethod.LLM_JUDGE,
    Dimension.RETRIEVAL_RECALL: EvalMethod.LLM_JUDGE,
    Dimension.CONTEXT_UTILIZATION: EvalMethod.LLM_JUDGE,
    Dimension.CONTEXT_RELEVANCE: EvalMethod.LLM_JUDGE,
    # agentic-only, retained
    Dimension.UNSAFE_TOOL_USE: EvalMethod.INJECTION_DETECTOR,
    Dimension.UNBOUNDED_CONSUMPTION: EvalMethod.DETERMINISTIC,
}


#: Reverse lookup: taxonomy name -> Dimension member (for focus resolution).
_NAME_TO_DIM: dict[str, Dimension] = {m.taxonomy_name: d for d, m in DIMENSION_META.items()}


def _norm(s: str) -> str:
    return str(s).strip().lower().replace(" ", "_").replace("-", "_")


def resolve_focus(items: object) -> frozenset[Dimension]:
    """Resolve a focus profile (taxonomy §2) to a set of Dimensions.

    Each item may be a category (e.g. ``"robustness"`` -> all its dims), a taxonomy name
    (``"prompt_injection_resistance"``), or a frozen Dimension value (``"injection_resistance"``).
    An unknown item raises. ``None`` / empty -> no focus.
    """

    if not items:
        return frozenset()
    _cat_by_value = {c.value: c for c in Category}
    _dim_by_value = {d.value: d for d in Dimension}
    dims: set[Dimension] = set()
    for item in items:
        key = _norm(item)
        if key in _cat_by_value:
            dims.update(DIMENSIONS_BY_CATEGORY[_cat_by_value[key]])
        elif key in _NAME_TO_DIM:
            dims.add(_NAME_TO_DIM[key])
        elif key in _dim_by_value:
            dims.add(_dim_by_value[key])
        else:
            raise ValueError(f"focus item {item!r} is not a known category or dimension")
    return frozenset(dims)


def _validate() -> None:
    """Fail loudly at import if the registry drifts from the enum (every dim registered exactly once)."""
    missing = [d.value for d in Dimension if d not in DIMENSION_META]
    if missing:
        raise ValueError(f"taxonomy.DIMENSION_META missing dimensions: {missing}")
    names = [m.taxonomy_name for m in DIMENSION_META.values()]
    dupes = sorted({n for n in names if names.count(n) > 1})
    if dupes:
        raise ValueError(f"taxonomy.DIMENSION_META has duplicate taxonomy names: {dupes}")
    unrouted = [d.value for d in Dimension if d not in DIMENSION_EVAL_METHOD]
    if unrouted:
        raise ValueError(f"taxonomy.DIMENSION_EVAL_METHOD missing dimensions: {unrouted}")


_validate()
