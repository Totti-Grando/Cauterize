"""Offline unit tests for A1: ClaudeQuestionGenerator + seeds.

No API key, no network: a fake Anthropic-shaped client is injected so the live path
(``client.messages.create(...)`` -> ``.content[0].text``) is exercised deterministically.
"""

from __future__ import annotations

import json

import pytest

from aah.contracts import Mode
from aah.layer_a.question_gen import (
    ClaudeQuestionGenerator,
    StubQuestionGenerator,
)
from aah.layer_a.seeds import (
    EXAMPLE_SEEDS,
    Seed,
    load_seed,
    load_seed_file,
    seed_to_text,
)


# --- Fake Anthropic client ----------------------------------------------------


class _FakeTextBlock:
    """Mimics a Messages API content block: has a ``.text`` and ``.type``."""

    def __init__(self, text: str):
        self.type = "text"
        self.text = text


class _FakeResponse:
    def __init__(self, text: str):
        self.content = [_FakeTextBlock(text)]


class _FakeMessages:
    def __init__(self, text: str):
        self._text = text
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return _FakeResponse(self._text)


class _FakeAnthropic:
    """Shaped like ``anthropic.Anthropic``: exposes ``.messages.create(...)``."""

    def __init__(self, text: str = "What were Acme's Q3 revenue and operating margin?"):
        self.messages = _FakeMessages(text)


# --- ClaudeQuestionGenerator --------------------------------------------------


def test_generate_returns_question_text():
    expected = "What were Acme's Q3 revenue and operating margin?"
    fake = _FakeAnthropic(text=expected)
    gen = ClaudeQuestionGenerator(client=fake)

    out = gen.generate("META PROMPT P_Q", "Domain: finance", Mode.QUALITY)

    assert out == expected


def test_generate_strips_whitespace():
    fake = _FakeAnthropic(text="   padded question?  \n")
    gen = ClaudeQuestionGenerator(client=fake)

    out = gen.generate("P_Q", "seed", Mode.QUALITY)

    assert out == "padded question?"


def test_generate_omits_temperature_and_passes_model():
    fake = _FakeAnthropic()
    gen = ClaudeQuestionGenerator(client=fake, model="claude-opus-4-8")

    gen.generate("P_Q", "Domain: finance", Mode.QUALITY)

    assert len(fake.messages.calls) == 1
    kwargs = fake.messages.calls[0]
    # Opus 4.7/4.8 rejects temperature; it must NOT be sent.
    assert "temperature" not in kwargs
    assert kwargs["model"] == "claude-opus-4-8"
    # The meta-prompt and seed both reach the model.
    assert "P_Q" in kwargs["system"]
    assert any("Domain: finance" in m["content"] for m in kwargs["messages"])


def test_generate_quality_vs_adversarial_instruction_differs():
    fake_q = _FakeAnthropic()
    fake_a = _FakeAnthropic()
    ClaudeQuestionGenerator(client=fake_q).generate("P_Q", "seed", Mode.QUALITY)
    ClaudeQuestionGenerator(client=fake_a).generate("P_Q", "seed", Mode.ADVERSARIAL)

    quality_system = fake_q.messages.calls[0]["system"]
    adversarial_system = fake_a.messages.calls[0]["system"]

    assert quality_system != adversarial_system
    assert "question" in quality_system.lower()
    assert "probe" in adversarial_system.lower()


def test_stub_still_present_and_echoes_seed():
    # Other tests depend on the stub; confirm it survives alongside the real impl.
    assert StubQuestionGenerator().generate("p", "the-seed", Mode.QUALITY) == "the-seed"


# --- seeds --------------------------------------------------------------------


def test_load_seed_roundtrip():
    d = {
        "domain": "finance",
        "source_doc": "Revenue was $4.2B.",
        "instructions": "Summarize faithfully.",
    }
    seed = load_seed(d)

    assert isinstance(seed, Seed)
    assert seed.domain == "finance"
    assert seed.source_doc == "Revenue was $4.2B."
    assert seed.instructions == "Summarize faithfully."


def test_seed_to_text_renders_all_fields():
    seed = load_seed({"domain": "finance", "source_doc": "X", "instructions": "Y"})
    text = seed_to_text(seed)

    assert "Domain: finance" in text
    assert "Instructions: Y" in text
    assert "X" in text


def test_seed_to_text_minimal():
    text = seed_to_text(load_seed({"domain": "finance"}))
    assert text == "Domain: finance"


def test_seed_is_frozen():
    seed = load_seed({"domain": "finance"})
    with pytest.raises(Exception):
        seed.domain = "other"  # frozen pydantic model


def test_example_seeds_render():
    assert "finance_summary" in EXAMPLE_SEEDS
    rendered = seed_to_text(EXAMPLE_SEEDS["finance_summary"])
    assert "finance" in rendered.lower()


def test_load_seed_file_json(tmp_path):
    p = tmp_path / "seed.json"
    p.write_text(
        json.dumps({"domain": "legal", "instructions": "Be precise."}),
        encoding="utf-8",
    )
    seed = load_seed_file(p)

    assert seed.domain == "legal"
    assert seed.instructions == "Be precise."


def test_generate_then_seed_text_feeds_generator():
    # End-to-end (offline): render a real seed, feed it through the generator.
    seed = EXAMPLE_SEEDS["finance_summary"]
    fake = _FakeAnthropic(text="Summarize Acme's Q3 results.")
    gen = ClaudeQuestionGenerator(client=fake)

    out = gen.generate("P_Q", seed_to_text(seed), Mode.QUALITY)

    assert out == "Summarize Acme's Q3 results."
    sent_seed = fake.messages.calls[0]["messages"][0]["content"]
    assert "Domain: finance" in sent_seed
