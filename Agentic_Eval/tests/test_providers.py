"""Offline unit tests for the provider-under-test adapters (spec §5 step 3a).

These run with no API key and no network: GeminiProvider takes an injectable client.
``asyncio_mode = "auto"`` (pyproject) lets the async tests run without a decorator.
"""

from __future__ import annotations

from aah.layer_a.providers import FixtureProvider, GeminiProvider


class _FakeResponse:
    def __init__(self, text: str):
        self.text = text


class _FakeClient:
    """Mirrors google.generativeai.GenerativeModel.generate_content(question)."""

    def __init__(self, text: str):
        self._text = text
        self.calls: list[str] = []

    def generate_content(self, question: str) -> _FakeResponse:
        self.calls.append(question)
        return _FakeResponse(self._text)


async def test_gemini_returns_response_text():
    fake = _FakeClient("hello there")
    provider = GeminiProvider(client=fake)

    result = await provider.query("hi")

    assert result == "hello there"
    assert fake.calls == ["hi"]
    assert provider.name == "gemini"


async def test_gemini_handles_empty_or_blocked_response():
    fake = _FakeClient("")
    provider = GeminiProvider(client=fake)

    assert await provider.query("anything") == ""


async def test_gemini_lazy_client_uses_temperature_zero(monkeypatch):
    """When no client is injected, the lazily built GenerativeModel must use temperature 0."""
    captured: dict[str, object] = {}

    class _FakeGenAI:
        @staticmethod
        def configure(api_key=None):
            captured["api_key"] = api_key

        @staticmethod
        def GenerativeModel(model, generation_config=None):
            captured["model"] = model
            captured["generation_config"] = generation_config
            return _FakeClient("lazy text")

    import sys

    monkeypatch.setitem(sys.modules, "google.generativeai", _FakeGenAI)

    provider = GeminiProvider(model="gemini-1.5-pro", api_key="test-key")
    result = await provider.query("hi")

    assert result == "lazy text"
    assert captured["api_key"] == "test-key"
    assert captured["model"] == "gemini-1.5-pro"
    assert captured["generation_config"] == {"temperature": 0}


async def test_fixture_canned_and_default():
    provider = FixtureProvider({"q1": "a1"}, default="fallback")

    assert await provider.query("q1") == "a1"
    assert await provider.query("unknown") == "fallback"
    assert provider.name == "fixture"
