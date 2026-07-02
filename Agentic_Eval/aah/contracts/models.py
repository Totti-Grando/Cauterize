"""Frozen data contracts (spec v3 §4). Freeze first; everything imports these.

Pydantic v2 models. ``explanation`` is mandatory on every Verdict -- it is both the
audit "why" and the fuel for the Layer B loop (spec §4, §8).
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from .enums import Dimension, EvalMethod, LessonKind, Mode, Subtype, Tier


class _Frozen(BaseModel):
    """Immutable, extra-forbidding base so contract drift fails loudly."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class Requirement(_Frozen):
    id: str
    dimension: Dimension
    text: str


class BinaryQuestion(_Frozen):
    """An atomic yes/no question, born tagged so a 0-verdict is pre-classified (§6).

    Produced by the two-step decomposition (§5): the task is first broken into Requirements
    (that should cover the task's domain), then each Requirement into atomic true/false
    questions. ``requirement_id`` / ``requirement_text`` link the question back to its parent
    requirement so the coverage is visible.
    """

    id: str
    requirement_id: str
    dimension: Dimension
    subtype: Subtype
    text: str
    violation_example: str
    eval_method: EvalMethod
    must_pass: bool = False  # a must-pass==0 forces an overall FAIL (gating, §7.4)
    requirement_text: str = ""  # the parent requirement this atomic check decomposes
    # Machine directive the scorer executes (``CHECK:...`` for deterministic, ``ATTACK:...`` for
    # injection). Kept SEPARATE from the human-readable ``violation_example`` so an LLM-generated
    # rubric can carry an executable directive without overloading the prose field. Scorers and
    # rubric normalization read this first and fall back to ``violation_example`` for legacy fixtures.
    check_directive: str = ""


class Verdict(_Frozen):
    """Scored answer to one BinaryQuestion. ``explanation`` is mandatory (§4, §8)."""

    question_id: str
    score: int = Field(ge=0, le=1)  # 0 | 1
    explanation: str = Field(min_length=1)
    evidence: Optional[str] = None
    attack_success: Optional[bool] = None  # adversarial mode signal (§8)


class DimensionScore(_Frozen):
    dimension: Dimension
    tier: Tier
    gating: bool
    score: float = Field(ge=0.0, le=1.0)
    weight: float = Field(ge=0.0, le=1.0)  # cross-dimension weight w_d (0 for gating dims)


class PruneThresholds(_Frozen):
    phi: float = 0.9                              # drop one of a pair above this |phi|
    yes_rate_band: tuple[float, float] = (0.05, 0.95)  # drop questions outside this band


class WeightConfig(_Frozen):
    """The only human input is the tier policy table. Same verdicts + same config => same score."""

    tiers: dict[Dimension, Tier]
    major_minor_ratio: float = 2.0  # MAJOR tierweight / MINOR tierweight (§7.3, only lever)
    prune_thresholds: PruneThresholds = PruneThresholds()
    gate_thresholds: dict[Dimension, float] = Field(default_factory=dict)  # per CRITICAL dim
    # F5: a gating dimension can absorb a single false positive by setting its threshold just
    # below 1.0 (must_pass checks ALWAYS stay zero-tolerance regardless of this). And when a
    # rubric contains any gating-dimension check, evaluate at >= gating_min_runs so noise damps
    # toward the safe side via conservative-to-fail averaging rather than a single flip deciding.
    gating_min_runs: int = 2
    version: str = "v0"


class RunScore(_Frozen):
    per_question: list[Verdict]
    per_dimension: list[DimensionScore]
    overall: float = Field(ge=0.0, le=1.0)
    failed: bool = False                 # True if gated to FAIL (§7.4)
    gated_by: Optional[Dimension] = None
    weight_config_version: str = "v0"


class JudgePolicy(_Frozen):
    """Self-enhancement-bias controls (F4). Documents how gating checks are judged when the
    evaluator shares a model family with the system-under-test.

    Defaults: flag same-family runs; when a cross-family reference is available, route the
    CRITICAL gating checks to it; an optional judge panel fails a gate if ANY panelist fails.
    Enforcement uses the ``gating_router`` / ``gating_panel`` arguments to ``run_once`` — this
    object is the declarative policy that a caller consults to decide whether to supply them.
    """

    flag_same_family: bool = True          # record provenance.same_family_judge
    cross_family_reference_for_gates: bool = True   # route CRITICAL gates to a cross-family judge
    panel_size: int = 1                    # >1 => run a panel on gating checks, fail if any fails


class Lesson(_Frozen):
    id: str
    source_question_ids: list[str]
    explanation_refs: list[str]
    text: str
    kind: LessonKind
    mode: Mode


class AgentInfo(_Frozen):
    """Identity of an LLM/agent that participated in a run (spec §7.6 + F1).

    ``model`` is the load-bearing field: verdicts come from a model, so "who judged" is as
    much a part of the audit as "what config." Populate from the RESOLVED runtime config, not
    defaults — two records with identical verdicts but a different ``model`` must be
    distinguishable.
    """

    backend: str = ""              # e.g. "bedrock" | "groq" | "anthropic" | "http" | "fixture" | "stub"
    model: str = ""                # resolved model id (never blank for a real emitted record)
    version: str = ""              # sdk/model/provider version if known
    params: dict[str, Any] = Field(default_factory=dict)  # temperature/top_p/seed if any


class Provenance(_Frozen):
    """Who judged and who was judged (F1). Stored on every AuditRecord."""

    evaluator: AgentInfo = Field(default_factory=AgentInfo)  # the judge (question/rubric/scorers)
    provider: AgentInfo = Field(default_factory=AgentInfo)   # the system-under-test
    same_family_judge: bool = False  # F4: evaluator_family == provider_family (self-enhancement risk)


class AuditRecord(_Frozen):
    """The full reproducible trail. Carries its WeightConfig so the score replays (§7.6),
    and its Provenance so "who judged" is recorded alongside "what config" (F1)."""

    mode: Mode
    task: str
    question: str                  # the generated domain question / attack
    response: str                  # provider-under-test response
    rubric: list[BinaryQuestion]
    verdicts: list[Verdict]
    scores: RunScore
    weight_config: WeightConfig
    prompt_version: str            # P_Q version that produced ``question``
    iteration: int = 0
    schema_version: str = "v1"     # bumped when the audit schema changes (F1 added provenance)
    provenance: Provenance = Field(default_factory=Provenance)
    yes_rate_summary: dict[str, float] = Field(default_factory=dict)  # F6: per-dimension yes-rate
