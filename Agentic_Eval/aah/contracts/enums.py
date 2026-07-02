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
    # generic
    OTHER = "other"


class Dimension(str, Enum):
    """The frozen dimension set (resolved spec §12). Tier is assigned in config.policy."""

    # CRITICAL (gating)
    INJECTION_RESISTANCE = "injection_resistance"        # direct + indirect
    DATA_LEAKAGE = "data_leakage"                        # system-prompt, PII, confidential context
    SOURCE_FABRICATION = "source_fabrication"
    REGULATORY_COMPLIANCE = "regulatory_compliance"
    UNSAFE_TOOL_USE = "unsafe_tool_use"                  # [agentic only] excessive agency
    # MAJOR (weight 2)
    FACTUAL_CONSISTENCY = "factual_consistency"          # grounding
    ANSWER_CORRECTNESS = "answer_correctness"
    RELEVANCE = "relevance"
    ROBUSTNESS = "robustness"                            # & stability
    ABSTENTION_CALIBRATION = "abstention_calibration"
    # MINOR (weight 1)
    COMPLETENESS = "completeness"
    INSTRUCTION_FOLLOWING = "instruction_following"
    SAFETY_FAIRNESS = "safety_fairness"
    UNBOUNDED_CONSUMPTION = "unbounded_consumption"      # [agentic only]


class LessonKind(str, Enum):
    """Promptable lessons patch P_Q; structural lessons are provider findings (spec §8, §9)."""

    PROMPTABLE = "promptable"
    STRUCTURAL = "structural"
