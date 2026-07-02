"""F9: the nli slot is a CONSTRAINED claim-checker (Claude/HTTP/local), not the general judge."""

from __future__ import annotations

import asyncio
import sys

from aah.contracts import Dimension, EvalMethod
from aah.layer_a.router import default_router
from aah.layer_a.scorers import ClaudeNLIScorer, HttpNLIScorer, LocalNLIScorer, make_nli
from aah.layer_a.scorers.nli import _SYSTEM as NLI_SYSTEM
from tests.conftest import make_question


def test_router_nli_slot_is_constrained_nli_not_judge():
    router = default_router()
    scorer = router._scorers[EvalMethod.NLI]
    assert isinstance(scorer, ClaudeNLIScorer)


def test_nli_prompt_is_constrained_supported_check():
    low = NLI_SYSTEM.lower()
    assert "support" in low  # "supports (entails) the CLAIM"
    assert '"supported": true|false' in NLI_SYSTEM  # tight JSON yes/no shape


def test_http_nli_uses_constrained_prompt_and_maps_yes_no():
    calls = []

    async def fake_poster(url, headers, payload):
        calls.append((url, headers, payload))
        return {"choices": [{"message": {"content": '{"supported": true, "reason": "entailed"}'}}]}

    scorer = HttpNLIScorer("https://gw.internal/v1/chat", model="nli-1", poster=fake_poster)
    q = make_question("n", Dimension.FACTUAL_CONSISTENCY, eval_method=EvalMethod.NLI)
    v = asyncio.run(scorer.score(q, "resp", "the source says X"))
    assert v.score == 1
    _url, _headers, payload = calls[0]
    assert payload["temperature"] == 0
    assert payload["model"] == "nli-1"
    assert payload["messages"][0]["content"] == NLI_SYSTEM  # constrained system prompt
    assert "UNTRUSTED_DATA" in payload["messages"][1]["content"]  # F2 fencing carries over


def test_http_nli_fails_closed_on_unparseable():
    async def fake_poster(url, headers, payload):
        return {"choices": [{"message": {"content": "garbled"}}]}

    scorer = HttpNLIScorer("https://gw", poster=fake_poster)
    q = make_question("n", Dimension.FACTUAL_CONSISTENCY, eval_method=EvalMethod.NLI)
    v = asyncio.run(scorer.score(q, "resp", "ctx"))
    assert v.score == 0


def test_make_nli_backends():
    assert isinstance(make_nli({"backend": "claude"}), ClaudeNLIScorer)
    assert isinstance(make_nli({"backend": "http", "url": "https://x"}), HttpNLIScorer)
    assert isinstance(make_nli({"backend": "local"}), LocalNLIScorer)
    assert isinstance(make_nli(None), ClaudeNLIScorer)  # default


def test_base_install_is_torch_free():
    import aah.layer_a.scorers  # noqa: F401 - importing the scorer package must not pull torch
    assert "torch" not in sys.modules
    assert "transformers" not in sys.modules
