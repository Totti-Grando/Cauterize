"""Frozen enumerations shared across every module (spec v3 §4, §6).

These are part of the data contract: changing a value here is a breaking change
to every AuditRecord ever written. Add members; do not rename or remove.
"""

from __future__ import annotations

from enum import Enum


class Mode(str, Enum):
    """Runtime flag on the one pipeline (spec §2)."""

    QUALITY = "quality"          # Quality-Eval: failure = low-quality / unfaithful answer
    ADVERSARIAL = "adversarial"  # Adversarial-Probe: failure = a successful attack
    HYBRID = "hybrid"            # interleave both; security dimensions gate


class Tier(str, Enum):
    """Dimension severity tier (spec §7.1). Drives gating + cross-dimension weight."""

    CRITICAL = "critical"  # gating
    MAJOR = "major"        # tierweight = major_minor_ratio (default 2)
    MINOR = "minor"        # tierweight = 1


class EvalMethod(str, Enum):
    """The router key: cheapest competent scorer per question (spec §4, §6)."""

    DETERMINISTIC = "deterministic"          # format, count, JSON-valid, contains, regex, cost
    NLI = "nli"                              # "is claim X supported by source?"
    INJECTION_DETECTOR = "injection_detector"  # "did the injection land?" (M4)
    SOURCE_FETCH = "source_fetch"            # open link, verify author/date/claim
    SOURCE_CHECK = "source_check"            # deterministic fabrication gate: cited sources ⊆ context (F3)
    LLM_JUDGE = "llm_judge"                  # holistic / subtle only


class Subtype(str, Enum):
    """Fine-grained failure category, tagged at rubric-generation time (spec §6).

    A ``0`` verdict is therefore already classified. The list below is the
    consistency family from §4 plus security families used in adversarial mode;
    extend per dimension as needed.
    """

    # consistency / faithfulness family (§4)
    UNSUPPORTED = "unsupported"
    FABRICATION = "fabrication"
    ENTITY_ERROR = "entity_error"
    NUMBER_ERROR = "number_error"
    CAUSAL_ERROR = "causal_error"
    MISATTRIBUTION = "misattribution"
    CONFLATION = "conflation"
    ABSTENTION_FAILURE = "abstention_failure"
    # security family (adversarial mode, M4)
    PROMPT_LEAK = "prompt_leak"
    PII_LEAK = "pii_leak"
    PAYLOAD_OBEYED = "payload_obeyed"
    FABRICATED_SOURCE = "fabricated_source"
    # taxonomy §1 gating subtypes (a scored MAJOR dim can veto on one of these; wired in aggregator)
    INVENTED_POLICY = "invented_policy"          # hallucination gate: an invented rule/policy
    CONSTRAINT_VIOLATION = "constraint_violation"  # constraint_compliance gate: safety/legal restriction breached
    INSECURE_ADVICE = "insecure_advice"          # security_compliance gate: actively insecure advice
    # generic
    OTHER = "other"


class Category(str, Enum):
    """The 10 taxonomy categories (taxonomy §1). A Category groups Dimensions for
    focus selection and reporting; it carries no tier or gating semantics itself."""

    RESPONSE_QUALITY = "response_quality"
    EVIDENCE_TRUTHFULNESS = "evidence_truthfulness"
    REASONING = "reasoning"
    INSTRUCTION_FOLLOWING = "instruction_following"
    COMMUNICATION = "communication"
    SAFETY = "safety"
    FAIRNESS = "fairness"
    PRIVACY_SECURITY = "privacy_security"
    ROBUSTNESS = "robustness"
    RAG_QUALITY = "rag_quality"


class Dimension(str, Enum):
    """The frozen dimension set. Values are audit keys written into every AuditRecord —
    add members, never rename or remove. Category, tier, and gating subtype are assigned
    in config (taxonomy.py / policy.py), not here.

    The original 16 members (below) are RETAINED and MAPPED to their taxonomy names via
    ``config.taxonomy.DIMENSION_META`` rather than renamed — e.g. the member
    ``INJECTION_RESISTANCE`` (value ``"injection_resistance"``) is the taxonomy dimension
    ``prompt_injection_resistance``. The 21 members under "taxonomy §1 additions" are the
    dimensions with no pre-existing member.
    """

    # --- original set (resolved spec §12) — values frozen, mapped in DIMENSION_META ---
    # CRITICAL (gating)
    INJECTION_RESISTANCE = "injection_resistance"        # -> prompt_injection_resistance
    DATA_LEAKAGE = "data_leakage"                        # -> confidential_data_exposure
    SOURCE_FABRICATION = "source_fabrication"            # -> hallucination (now MAJOR + gating subtype)
    REGULATORY_COMPLIANCE = "regulatory_compliance"      # -> constraint_compliance (now MAJOR + gating subtype)
    UNSAFE_TOOL_USE = "unsafe_tool_use"                  # [agentic only] excessive agency — retained
    HARM = "harm"                                        # -> harmfulness (Layer C G13; own gate)
    # MAJOR (weight 2)
    FACTUAL_CONSISTENCY = "factual_consistency"          # -> groundedness
    ANSWER_CORRECTNESS = "answer_correctness"            # -> accuracy
    RELEVANCE = "relevance"                              # -> relevance
    ROBUSTNESS = "robustness"                            # -> paraphrase_stability
    ABSTENTION_CALIBRATION = "abstention_calibration"    # -> uncertainty_handling
    EXPLAINABILITY = "explainability"                    # -> logical_consistency (Layer C G12)
    # MINOR (weight 1)
    COMPLETENESS = "completeness"                        # -> completeness (now MAJOR)
    INSTRUCTION_FOLLOWING = "instruction_following"      # -> format_compliance
    SAFETY_FAIRNESS = "safety_fairness"                  # -> bias (now MAJOR)
    UNBOUNDED_CONSUMPTION = "unbounded_consumption"      # [agentic only] — retained

    # --- taxonomy §1 additions (21 new dimensions) ---------------------------------
    # Response Quality
    TASK_SUCCESS = "task_success"
    # Evidence & Truthfulness
    SOURCE_QUALITY = "source_quality"
    SOURCE_ATTRIBUTION = "source_attribution"
    # Reasoning
    ASSUMPTION_QUALITY = "assumption_quality"
    # Instruction Following
    PERSONA_COMPLIANCE = "persona_compliance"
    # Communication
    CLARITY = "clarity"
    STRUCTURE = "structure"
    CONCISENESS = "conciseness"
    ACTIONABILITY = "actionability"
    # Safety
    TOXICITY = "toxicity"
    REFUSAL_QUALITY = "refusal_quality"
    # Fairness
    STEREOTYPING = "stereotyping"
    # Privacy & Security
    PII_LEAKAGE = "pii_leakage"
    PROMPT_LEAKAGE = "prompt_leakage"
    SECURITY_COMPLIANCE = "security_compliance"
    # Robustness
    JAILBREAK_RESISTANCE = "jailbreak_resistance"
    ADVERSARIAL_ROBUSTNESS = "adversarial_robustness"
    # RAG Quality
    RETRIEVAL_PRECISION = "retrieval_precision"
    RETRIEVAL_RECALL = "retrieval_recall"
    CONTEXT_UTILIZATION = "context_utilization"
    CONTEXT_RELEVANCE = "context_relevance"


class LessonKind(str, Enum):
    """Promptable lessons patch P_Q; structural lessons are provider findings (spec §8, §9)."""

    PROMPTABLE = "promptable"
    STRUCTURAL = "structural"


# --- Layer C governance enums (Stage 1) --------------------------------------------
class Band(str, Enum):
    """G/A/R severity band for a governed metric. There is deliberately NO Yellow —
    only Green / Amber / Red plus the numeric Likelihood×Impact (spec: governance §5)."""

    GREEN = "green"
    AMBER = "amber"
    RED = "red"


class Trend(str, Enum):
    """Direction of a metric over its time-series (worsening / improving / stable)."""

    UP = "up"        # worsening
    DOWN = "down"    # improving
    FLAT = "flat"


class Disposition(str, Enum):
    """The governance decision for a use case (governance §9). A gated run — a critical Red
    or a must-pass failure — can never resolve to APPROVE."""

    APPROVE = "approve"
    APPROVE_WITH_CONDITIONS = "approve_with_conditions"
    REMEDIATE = "remediate"
    ESCALATE = "escalate"
    ACCEPT_RISK = "accept_risk"


class LineOfDefence(str, Enum):
    """3LoD reviewer role: 1st = accountable owner, 2nd = challenge, 3rd = audit."""

    FIRST = "first"
    SECOND = "second"
    THIRD = "third"
