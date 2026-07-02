"""Offline tests for the provider-agnostic LLM layer (aah.llm)."""

from __future__ import annotations

import aah.llm as llm
from aah.layer_a.scorers.base import extract_text


def test_resolve_groq_key_is_explicit_only(monkeypatch):
    # Audit finding #19: resolution must NOT scan arbitrary env values for a gsk_ prefix
    # (that could authenticate with an unrelated secret). Only GROQ_API_KEY is honored.
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setenv("SOMETHING_ELSE", "gsk_unrelated")
    assert llm.resolve_groq_key() is None                  # no longer auto-detected
    monkeypatch.setenv("GROQ_API_KEY", "gsk_explicit")
    assert llm.resolve_groq_key() == "gsk_explicit"        # explicit variable only


def test_wrap_is_anthropic_shaped():
    # The shim's response must read like an Anthropic message for the Claude* components.
    msg = llm._wrap("hello")
    assert extract_text(msg) == "hello"


def test_content_extraction_from_openai_shape():
    data = {"choices": [{"message": {"content": "the answer"}}]}
    assert llm._content(data) == "the answer"
    assert llm._content({"choices": []}) == ""            # malformed -> empty, no crash


def test_make_evaluator_groq_without_key_raises(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    for k in list(__import__("os").environ):
        if __import__("os").environ[k].startswith("gsk_"):
            monkeypatch.delenv(k, raising=False)
    try:
        llm.make_evaluator("groq")
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "Groq key" in str(exc)
