"""Offline tests for the A4 scorers (spec §5 step 5, §6).

No network / API key required: the LLM scorers take an injected fake Anthropic client and
the source-fetch scorer takes a fake fetcher + stub nli.
"""

from __future__ import annotations

import asyncio

from aah.contracts import BinaryQuestion, Dimension, EvalMethod, Subtype, Verdict
from aah.layer_a.scorers import (
    ClaudeJudgeScorer,
    ClaudeNLIScorer,
    DeterministicScorer,
    InjectionDetectorScorer,
    SourceFetchScorer,
)
from aah.layer_a.scorers.deterministic import (
    contains,
    json_valid,
    max_words,
    not_contains,
    parse_check,
    regex_match,
    url_present,
)
from aah.layer_a.scorers.source_fetch import extract_url


# -- helpers ---------------------------------------------------------------------------
def make_question(
    qid: str = "q1",
    *,
    text: str = "is the claim supported?",
    violation_example: str = "a bad answer",
    eval_method: EvalMethod = EvalMethod.DETERMINISTIC,
) -> BinaryQuestion:
    return BinaryQuestion(
        id=qid,
        requirement_id=f"req-{qid}",
        dimension=Dimension.FACTUAL_CONSISTENCY,
        subtype=Subtype.UNSUPPORTED,
        text=text,
        violation_example=violation_example,
        eval_method=eval_method,
    )


class _FakeBlock:
    def __init__(self, text: str):
        self.type = "text"
        self.text = text


class _FakeMessage:
    def __init__(self, text: str):
        self.content = [_FakeBlock(text)]


class FakeAnthropicClient:
    """Records every ``messages.create`` call and returns a canned text block."""

    def __init__(self, reply_text: str):
        self._reply_text = reply_text
        self.calls: list[dict] = []
        self.messages = self  # so ``client.messages.create`` resolves here

    async def create(self, **kwargs) -> _FakeMessage:
        self.calls.append(kwargs)
        return _FakeMessage(self._reply_text)


class StubNLI:
    """A fake/stub nli scorer that records the context it was claim-checked against."""

    def __init__(self, score: int = 1):
        self._score = score
        self.contexts: list[str] = []

    async def score(self, question, response, context) -> Verdict:
        self.contexts.append(context)
        return Verdict(question_id=question.id, score=self._score, explanation="stub nli")


# -- deterministic primitives ----------------------------------------------------------
def test_json_valid():
    assert json_valid('{"a": 1}') is True
    assert json_valid("  [1, 2, 3] ") is True
    assert json_valid("not json") is False
    assert json_valid("") is False


def test_contains_and_not_contains():
    assert contains("Hello World", "world") is True
    assert contains("Hello", "bye") is False
    assert not_contains("Hello", "bye") is True
    assert not_contains("Hello World", "world") is False


def test_regex_match():
    assert regex_match("order #4821", r"#\d+") is True
    assert regex_match("no number", r"#\d+") is False
    assert regex_match("anything", "(") is False  # bad pattern fails closed


def test_max_words():
    assert max_words("one two three", 3) is True
    assert max_words("one two three four", 3) is False
    assert max_words("", 0) is True


def test_url_present_and_extract_url():
    assert url_present("see https://example.com/x for more") is True
    assert url_present("no link here") is False
    assert extract_url("a https://example.com/p b") == "https://example.com/p"
    assert extract_url("nothing") is None


# -- CHECK: parsing --------------------------------------------------------------------
def test_parse_check():
    assert parse_check("CHECK:json_valid") == ("json_valid", None)
    assert parse_check("CHECK:contains=foo") == ("contains", "foo")
    assert parse_check("  CHECK:max_words=50 ") == ("max_words", "50")
    assert parse_check("not a directive") is None
    assert parse_check("") is None


# -- DeterministicScorer (no fakes needed) ---------------------------------------------
def test_deterministic_no_check_default():
    q = make_question(violation_example="just a plain example, no directive")
    v = asyncio.run(DeterministicScorer().score(q, "any response", "ctx"))
    assert v.score == 1
    assert v.explanation == "no deterministic check specified"


def test_deterministic_json_valid_pass_and_fail():
    q = make_question(violation_example="CHECK:json_valid")
    ok = asyncio.run(DeterministicScorer().score(q, '{"k": 1}', ""))
    assert ok.score == 1 and ok.explanation
    bad = asyncio.run(DeterministicScorer().score(q, "oops", ""))
    assert bad.score == 0 and bad.explanation


def test_deterministic_contains_directive():
    q = make_question(violation_example="CHECK:contains=summary")
    ok = asyncio.run(DeterministicScorer().score(q, "Here is the summary.", ""))
    assert ok.score == 1
    bad = asyncio.run(DeterministicScorer().score(q, "Here is nothing.", ""))
    assert bad.score == 0


def test_deterministic_max_words_directive():
    q = make_question(violation_example="CHECK:max_words=3")
    assert asyncio.run(DeterministicScorer().score(q, "a b c", "")).score == 1
    assert asyncio.run(DeterministicScorer().score(q, "a b c d", "")).score == 0


def test_deterministic_url_present_directive():
    q = make_question(violation_example="CHECK:url_present")
    assert asyncio.run(DeterministicScorer().score(q, "see http://x.io", "")).score == 1
    assert asyncio.run(DeterministicScorer().score(q, "no link", "")).score == 0


def test_deterministic_unknown_check_abstains():
    q = make_question(violation_example="CHECK:does_not_exist")
    v = asyncio.run(DeterministicScorer().score(q, "x", ""))
    assert v.score == 1 and "unknown" in v.explanation


# -- ClaudeNLIScorer (fake client) -----------------------------------------------------
def test_nli_supported_true():
    client = FakeAnthropicClient('{"supported": true, "reason": "context entails claim"}')
    q = make_question(eval_method=EvalMethod.NLI)
    v = asyncio.run(ClaudeNLIScorer(client=client).score(q, "resp", "the context"))
    assert v.score == 1
    assert v.explanation  # mandatory, non-empty
    # Opus 4.7/4.8 rejects temperature; it must NOT be sent on the LLM call.
    assert client.calls and "temperature" not in client.calls[0]
    assert client.calls[0]["model"] == "claude-opus-4-8"


def test_nli_unsupported_false():
    client = FakeAnthropicClient('{"supported": false, "reason": "context is silent"}')
    q = make_question(eval_method=EvalMethod.NLI)
    v = asyncio.run(ClaudeNLIScorer(client=client).score(q, "resp", "ctx"))
    assert v.score == 0
    assert v.explanation


# -- ClaudeJudgeScorer (fake client) ---------------------------------------------------
def test_judge_yes():
    client = FakeAnthropicClient('{"answer": "yes", "reason": "faithful and relevant"}')
    q = make_question(eval_method=EvalMethod.LLM_JUDGE)
    v = asyncio.run(ClaudeJudgeScorer(client=client).score(q, "resp", "ctx"))
    assert v.score == 1
    assert v.explanation
    # Opus 4.7/4.8 rejects temperature; it must NOT be sent on the LLM call.
    assert "temperature" not in client.calls[0]


def test_judge_no():
    client = FakeAnthropicClient('{"answer": "no", "reason": "misrepresents the source"}')
    q = make_question(eval_method=EvalMethod.LLM_JUDGE)
    v = asyncio.run(ClaudeJudgeScorer(client=client).score(q, "resp", "ctx"))
    assert v.score == 0
    assert v.explanation


# -- SourceFetchScorer (fake fetcher + stub nli) ---------------------------------------
def test_source_fetch_fetches_then_claim_checks():
    stub = StubNLI(score=1)
    fetched = []

    def fake_fetcher(url: str) -> str:
        fetched.append(url)
        return "PAGE TEXT THAT SUPPORTS THE CLAIM"

    scorer = SourceFetchScorer(nli=stub, fetcher=fake_fetcher)
    q = make_question(eval_method=EvalMethod.SOURCE_FETCH)
    v = asyncio.run(scorer.score(q, "source: https://example.com/article", ""))

    assert fetched == ["https://example.com/article"]  # it fetched the URL
    assert stub.contexts == ["PAGE TEXT THAT SUPPORTS THE CLAIM"]  # nli got the page text
    assert v.score == 1
    assert v.explanation
    assert v.evidence == "https://example.com/article"  # source recorded as evidence


def test_source_fetch_url_from_context():
    stub = StubNLI(score=1)
    scorer = SourceFetchScorer(nli=stub, fetcher=lambda url: "text")
    q = make_question(eval_method=EvalMethod.SOURCE_FETCH)
    v = asyncio.run(scorer.score(q, "no link in response", "ref http://src.example/p"))
    assert v.score == 1
    assert v.evidence == "http://src.example/p"


def test_source_fetch_no_url():
    stub = StubNLI()
    scorer = SourceFetchScorer(nli=stub, fetcher=lambda url: "text")
    q = make_question(eval_method=EvalMethod.SOURCE_FETCH)
    v = asyncio.run(scorer.score(q, "no link", "no link"))
    assert v.score == 0
    assert v.explanation
    assert stub.contexts == []  # never reached the nli claim-check


def test_source_fetch_empty_page():
    stub = StubNLI()
    scorer = SourceFetchScorer(nli=stub, fetcher=lambda url: "")
    q = make_question(eval_method=EvalMethod.SOURCE_FETCH)
    v = asyncio.run(scorer.score(q, "see https://example.com", ""))
    assert v.score == 0
    assert stub.contexts == []


# -- InjectionDetectorScorer (real, M4) ------------------------------------------------
def test_injection_detector_abstains_without_directive():
    # A question carrying no ATTACK: directive abstains (score=1, no attack landed).
    q = make_question(eval_method=EvalMethod.INJECTION_DETECTOR)
    v = asyncio.run(InjectionDetectorScorer().score(q, "resp", "ctx"))
    assert v.score == 1
    assert v.attack_success is False
    assert v.explanation == "no attack check specified"
