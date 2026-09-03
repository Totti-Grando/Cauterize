"""Offline tests for the Bedrock evaluator backend and the generic HTTP provider."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import aah.model_clients as llm
from aah.layer_a.providers.http import HttpProvider, _get_path, _set_path


# --- Bedrock evaluator backend ------------------------------------------------

def test_make_evaluator_bedrock_wires_clients_and_region(monkeypatch):
    captured = {}

    class _FakeBedrock:
        def __init__(self, **kwargs):
            captured["sync"] = kwargs

    class _FakeAsyncBedrock:
        def __init__(self, **kwargs):
            captured["async"] = kwargs

    fake_anthropic = SimpleNamespace(
        AnthropicBedrock=_FakeBedrock, AsyncAnthropicBedrock=_FakeAsyncBedrock
    )
    monkeypatch.setitem(__import__("sys").modules, "anthropic", fake_anthropic)
    monkeypatch.setenv("AWS_REGION", "us-west-2")

    sync, asyncc, model = llm.make_evaluator("bedrock")
    assert isinstance(sync, _FakeBedrock) and isinstance(asyncc, _FakeAsyncBedrock)
    assert captured["sync"] == {"aws_region": "us-west-2"}         # region threaded through
    assert model == llm.DEFAULT_BEDROCK_EVAL_MODEL                 # global.anthropic...opus-4-6


def test_make_evaluator_bedrock_model_override(monkeypatch):
    monkeypatch.setitem(
        __import__("sys").modules, "anthropic",
        SimpleNamespace(AnthropicBedrock=lambda **k: object(),
                        AsyncAnthropicBedrock=lambda **k: object()),
    )
    monkeypatch.delenv("AWS_REGION", raising=False)
    monkeypatch.delenv("AWS_DEFAULT_REGION", raising=False)
    _, _, model = llm.make_evaluator("bedrock", "us.anthropic.claude-opus-4-6-v1")
    assert model == "us.anthropic.claude-opus-4-6-v1"


# --- dot-path helpers ---------------------------------------------------------

def test_dot_path_set_and_get_with_list_index():
    body: dict = {}
    _set_path(body, "messages.0.content", "hi")
    assert body == {"messages": [{"content": "hi"}]}
    assert _get_path(body, "messages.0.content") == "hi"
    assert _get_path(body, "missing.key") == ""


# --- generic HTTP provider ----------------------------------------------------

def test_http_provider_builds_payload_and_extracts_answer(monkeypatch):
    seen = {}

    async def fake_poster(url, headers, payload):
        seen["url"] = url
        seen["headers"] = headers
        seen["payload"] = payload
        return {"choices": [{"message": {"content": "the answer"}}]}

    monkeypatch.setenv("BANK_TOKEN", "secret-123")
    provider = HttpProvider(
        "https://model.example/api",
        question_path="messages.0.content",
        response_path="choices.0.message.content",
        base_payload={"model": "bank-llm", "messages": [{"role": "user"}]},
        api_key_env="BANK_TOKEN",
        poster=fake_poster,
    )
    answer = asyncio.run(provider.query("What were Q3 results?"))

    assert answer == "the answer"
    assert seen["payload"]["messages"][0]["content"] == "What were Q3 results?"
    assert seen["payload"]["model"] == "bank-llm"
    assert seen["headers"]["Authorization"] == "Bearer secret-123"


def test_http_provider_prompt_style_and_missing_field(monkeypatch):
    async def fake_poster(url, headers, payload):
        return {"output": {"text": "grounded reply"}}

    provider = HttpProvider(
        "https://model.example/complete",
        question_path="prompt",
        response_path="output.text",
        poster=fake_poster,
    )
    assert asyncio.run(provider.query("hi")) == "grounded reply"
