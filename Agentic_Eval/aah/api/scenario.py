"""Offline demo scenario: run the REAL Layer A pipeline with deterministic fixtures.

No API keys, no network, no cost — every rubric check is a ``deterministic`` CHECK the
DeterministicScorer runs locally, and each provider answer is a canned FixtureProvider
string. The cases are hand-built so the five evaluations land on genuinely different
verdicts (correct / partial / incorrect-gated / unverifiable), which is what makes the
Results dashboard look alive.

This is the seam to swap for a live run: replace ``FixtureProvider`` with a real provider
and ``StubRubricGenerator`` with the Claude-backed generator (see aah/cli.py `_run_live`).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..contracts import AuditRecord, BinaryQuestion, Dimension, EvalMethod, Mode, Subtype
from ..layer_a.pipeline import run_once
from ..layer_a.providers import FixtureProvider
from ..layer_a.question_gen import StubQuestionGenerator
from ..layer_a.router import default_router
from ..layer_a.rubric_gen import StubRubricGenerator


@dataclass(frozen=True)
class Check:
    """One atomic rubric check. ``directive`` is a DeterministicScorer CHECK: string;
    an empty directive makes the scorer abstain (score=1, "no check specified")."""

    dimension: Dimension
    subtype: Subtype
    text: str
    directive: str = ""
    must_pass: bool = False


@dataclass(frozen=True)
class Case:
    """A demo question + the provider's canned answer + the rubric to grade it with."""

    id: str
    persona: str
    category: str
    difficulty: str
    focus: list[str]
    question: str
    why: str
    expected: str
    response: str
    checks: list[Check]
    status: str = "pending"
    evidence: list[dict] = field(default_factory=list)


# --- Evidence snippets reused across cases (illustrative; no real data) --------------
_EV_ESG = {
    "id": "ev1",
    "title": "ESG controversy resurfaces for issuer",
    "domain": "research.example.com",
    "support": "partial",
    "quote": "Analysts flagged renewed scrutiny over the issuer's supply-chain disclosures following an August report.",
    "author": "J. Marchetti",
    "published": "2026-08-04",
    "canonicalUrl": "https://research.example.com/issuer/esg-controversy-aug",
    "sourceUrl": "https://research.example.com/issuer/esg-controversy-aug",
    "fetchSuccess": True,
    "textLength": 8421,
}
_EV_REG = {
    "id": "ev2",
    "title": "Regulator opens inquiry into disclosures",
    "domain": "newswire.example.com",
    "support": "strong",
    "quote": "A regulator confirmed an inquiry into the issuer's recent disclosures was opened this month.",
    "author": "Newswire Staff",
    "published": "2026-08-15",
    "canonicalUrl": "https://newswire.example.com/2026/regulatory-inquiry",
    "sourceUrl": "https://newswire.example.com/2026/regulatory-inquiry",
    "fetchSuccess": True,
    "textLength": 5210,
}
_EV_PORTAL = {
    "id": "ev3",
    "title": "Secure filings portal",
    "domain": "portal.example.com",
    "support": "not_evaluable",
    "quote": "",
    "author": None,
    "published": None,
    "canonicalUrl": "https://portal.example.com/secure/filings",
    "sourceUrl": "https://portal.example.com/secure/filings",
    "fetchSuccess": False,
    "textLength": 0,
}


CASES: list[Case] = [
    # 1) Reputational risk — PARTIAL: grounded event named, but scope omitted + ungrounded stat.
    Case(
        id="Q-001",
        persona="Risk Analyst",
        category="Reputational risk",
        difficulty="Hard",
        focus=["Groundedness", "Missing information"],
        question="Over the last 30 days, what source-grounded evidence suggests increased reputational risk for the selected issuer?",
        why="Tests whether the provider can tie a risk claim to dated, source-grounded evidence rather than general sentiment.",
        expected="Cites at least two dated sources describing specific reputational events and flags the login-blocked filing as unavailable.",
        response=(
            "Over the trailing 30 days, sentiment declined modestly, driven by an ESG controversy "
            "reported in early August and a regulatory inquiry disclosed mid-month. Coverage volume "
            "rose ~18% with a negative skew. A filing portal was referenced but could not be retrieved."
        ),
        checks=[
            Check(Dimension.FACTUAL_CONSISTENCY, Subtype.MISATTRIBUTION, "Names a dated reputational event", "CHECK:contains=August"),
            Check(Dimension.ANSWER_CORRECTNESS, Subtype.NUMBER_ERROR, "Provides a quantitative sentiment figure", "CHECK:regex_match=\\d+%"),
            Check(Dimension.FACTUAL_CONSISTENCY, Subtype.UNSUPPORTED, "Attributes the coverage figure to a source", "CHECK:contains=according to"),
            Check(Dimension.COMPLETENESS, Subtype.ABSTENTION_FAILURE, "States the regulatory inquiry's scope", "CHECK:contains=scope"),
        ],
        evidence=[_EV_ESG, _EV_REG, _EV_PORTAL],
    ),
    # 2) Regulatory — CORRECT: every check passes.
    Case(
        id="Q-002",
        persona="Compliance Officer",
        category="Regulatory",
        difficulty="Medium",
        focus=["Accuracy", "Source quality"],
        question="Which regulatory inquiries referenced in the provided sources are still open, and what is their stated scope?",
        why="Checks extraction of regulatory status from documents vs. fabricated detail.",
        expected="Lists only inquiries present in sources, with scope quoted or paraphrased and dates attributed.",
        response=(
            "One regulatory inquiry was disclosed mid-month and remains open. According to the newswire "
            "report, its scope concerns the issuer's recent disclosures; no resolution date was provided."
        ),
        checks=[
            Check(Dimension.FACTUAL_CONSISTENCY, Subtype.UNSUPPORTED, "Attributes the inquiry to a source", "CHECK:contains=according to"),
            Check(Dimension.COMPLETENESS, Subtype.ABSTENTION_FAILURE, "States the inquiry's scope", "CHECK:contains=scope"),
            Check(Dimension.ANSWER_CORRECTNESS, Subtype.OTHER, "States the open/closed status", "CHECK:contains=open"),
        ],
        evidence=[_EV_REG],
    ),
    # 3) Market sentiment — PARTIAL: names a contradiction, but no supporting datapoint.
    Case(
        id="Q-003",
        persona="Portfolio Manager",
        category="Market sentiment",
        difficulty="Easy",
        focus=["Completeness", "Contradiction detection"],
        question="Summarize the net sentiment trend for the issuer over the briefing period and note any contradictory signals.",
        why="Surfaces whether the provider reconciles conflicting signals or cherry-picks.",
        expected="Gives a directional trend with at least one supporting datapoint and explicitly names contradictions.",
        response=(
            "Net sentiment trended negative overall, though a mid-period product announcement briefly "
            "lifted sentiment before coverage normalized."
        ),
        checks=[
            Check(Dimension.ANSWER_CORRECTNESS, Subtype.OTHER, "States a directional trend", "CHECK:contains=negative"),
            Check(Dimension.COMPLETENESS, Subtype.OTHER, "Names a contradictory signal", "CHECK:contains=though"),
            Check(Dimension.ANSWER_CORRECTNESS, Subtype.NUMBER_ERROR, "Cites a supporting datapoint", "CHECK:regex_match=\\d+%"),
        ],
        evidence=[],
    ),
    # 4) ESG — INCORRECT (gated): overclaims materiality (a must-pass grounding check fails).
    Case(
        id="Q-004",
        persona="Research Lead",
        category="ESG",
        difficulty="Hard",
        focus=["Hallucination resistance", "Reasoning quality"],
        question="Does the ESG controversy described in the August article materially change the issuer risk profile? Justify.",
        why="Probes reasoning quality and resistance to overclaiming materiality.",
        expected="Reasoned judgment grounded in the article, avoiding unsupported materiality conclusions.",
        response=(
            "Yes — the controversy materially increases the risk profile and should trigger a rating review."
        ),
        checks=[
            # must_pass: overclaiming materiality is a hard grounding failure -> gates the run.
            Check(Dimension.FACTUAL_CONSISTENCY, Subtype.UNSUPPORTED, "Does not overclaim unsupported materiality", "CHECK:not_contains=materially", must_pass=True),
            Check(Dimension.ANSWER_CORRECTNESS, Subtype.FABRICATION, "Does not invent an action not in scope", "CHECK:not_contains=rating review"),
            Check(Dimension.FACTUAL_CONSISTENCY, Subtype.UNSUPPORTED, "Grounds the judgment in the article", "CHECK:contains=article"),
        ],
        evidence=[_EV_ESG],
    ),
    # 5) Liquidity — UNVERIFIABLE: only holistic checks with no deterministic directive (all abstain).
    Case(
        id="Q-005",
        persona="Risk Analyst",
        category="Liquidity",
        difficulty="Medium",
        focus=["Accuracy", "Missing information"],
        question="What liquidity indicators are available in the sources, and which expected indicators are missing?",
        why="Tests explicit acknowledgment of missing information.",
        expected="Reports available indicators and names the gaps rather than inferring them.",
        response=(
            "The sources do not contain liquidity indicators. Expected indicators such as bid-ask "
            "spreads and turnover are not present."
        ),
        checks=[
            # No CHECK: directive -> the deterministic scorer abstains -> adapter marks unverifiable.
            Check(Dimension.RELEVANCE, Subtype.OTHER, "Answer requires holistic judgement (no deterministic check)"),
            Check(Dimension.COMPLETENESS, Subtype.OTHER, "Missing-indicator claim needs source verification"),
        ],
        evidence=[],
    ),
]


def _build_rubric(case: Case) -> list[BinaryQuestion]:
    """Turn a case's checks into born-tagged BinaryQuestions (all deterministic, offline)."""
    rubric: list[BinaryQuestion] = []
    for i, c in enumerate(case.checks):
        rubric.append(
            BinaryQuestion(
                id=f"{case.id}-c{i}",
                requirement_id=f"{case.id}-r{i}",
                requirement_text=c.text,
                dimension=c.dimension,
                subtype=c.subtype,
                text=c.text,
                violation_example=c.directive,  # the CHECK: directive the scorer reads
                eval_method=EvalMethod.DETERMINISTIC,
                must_pass=c.must_pass,
            )
        )
    return rubric


async def run_case(case: Case) -> AuditRecord:
    """Run one case through the real Layer A pipeline (offline, deterministic)."""
    return await run_once(
        seed=case.question,
        p_q="P_Q@demo",
        mode=Mode.QUALITY,
        generator=StubQuestionGenerator(),          # echoes the seed => question = case.question
        provider=FixtureProvider(default=case.response),
        rubric_gen=StubRubricGenerator(_build_rubric(case)),
        router=default_router(),                     # deterministic checks run with no client
        prompt_version="P_Q@demo",
    )


async def run_scenario() -> list[tuple[Case, AuditRecord]]:
    """Run every demo case; return (case, AuditRecord) pairs for the adapter."""
    return [(case, await run_case(case)) for case in CASES]


# --- fixture components for the streaming fallback (engine.py) ------------------------
def fixture_provider(case: Case) -> FixtureProvider:
    """A deterministic provider that returns the case's canned answer."""
    return FixtureProvider(default=case.response)


def fixture_rubric_gen(case: Case) -> StubRubricGenerator:
    """A rubric generator that yields the case's hand-built deterministic checks."""
    return StubRubricGenerator(_build_rubric(case))


def case_meta(case: Case, provider_label: str) -> dict:
    """The UI-only metadata the adapter needs (id/persona/category/expected/evidence)."""
    return {
        "id": f"E-{case.id.split('-')[-1]}",
        "questionId": case.id,
        "provider": provider_label,
        "persona": case.persona,
        "category": case.category,
        "expected": case.expected,
        "evidence": case.evidence,
    }


def generic_fixture(question: str) -> tuple[FixtureProvider, StubRubricGenerator, dict]:
    """Offline stand-in for a single ad-hoc (manual-mode) question with no live provider.

    Returns a provider that echoes a plausible placeholder answer, a small deterministic
    rubric, and UI meta — so manual mode still streams a real evaluation with no keys.
    """
    answer = (
        "(offline demo — no live provider configured) Based on the available context, here is a "
        "placeholder answer. According to the sources, the key points are summarized above; some "
        "details could not be fully verified."
    )
    rubric = StubRubricGenerator([
        BinaryQuestion(
            id="manual-c0", requirement_id="manual-r0",
            requirement_text="Attributes claims to a source",
            dimension=Dimension.FACTUAL_CONSISTENCY, subtype=Subtype.UNSUPPORTED,
            text="Attributes claims to a source", violation_example="CHECK:contains=according to",
            eval_method=EvalMethod.DETERMINISTIC,
        ),
        BinaryQuestion(
            id="manual-c1", requirement_id="manual-r1",
            requirement_text="Acknowledges verification limits",
            dimension=Dimension.COMPLETENESS, subtype=Subtype.ABSTENTION_FAILURE,
            text="Acknowledges verification limits", violation_example="CHECK:contains=verified",
            eval_method=EvalMethod.DETERMINISTIC,
        ),
    ])
    meta = {
        "id": "E-MANUAL", "questionId": "MANUAL", "provider": "Offline demo",
        "persona": "User", "category": "Manual", "expected": "", "evidence": [],
    }
    return FixtureProvider(default=answer), rubric, meta
