"""R6: the focus profile steers rubric generation (deeper focus-area checks) without dropping
coverage; the security-dimension list stays in sync with the routing table."""

from __future__ import annotations

import json

from aah.layer_a.rubric_gen import ClaudeRubricGenerator, StagedRubricGenerator, _injection_dims_phrase
from tests.test_rubric_gen import _FakeAnthropic, _canned_items


def _prompt_of(fake) -> str:
    return fake.captured["messages"][0]["content"]


def test_no_focus_has_no_focus_directive():
    fake = _FakeAnthropic(json.dumps(_canned_items()))
    ClaudeRubricGenerator(client=fake).build("Summarize the article.")
    assert "FOCUS AREAS" not in _prompt_of(fake)


def test_focus_injects_directive_into_the_prompt():
    fake = _FakeAnthropic(json.dumps(_canned_items()))
    ClaudeRubricGenerator(client=fake, focus=["robustness"]).build("Summarize the article.")
    prompt = _prompt_of(fake)
    assert "FOCUS AREAS" in prompt
    assert "robustness" in prompt
    assert "MORE and DEEPER checks" in prompt
    # coverage is preserved — the full dimension list is still offered to the generator
    assert "dimension:" in prompt


def test_security_dims_phrase_tracks_the_routing_table():
    phrase = _injection_dims_phrase()
    # the genuine security-probe dims (injection_detector) are listed, quality dims are not
    assert "injection_resistance" in phrase
    assert "jailbreak_resistance" in phrase
    assert "pii_leakage" in phrase
    assert "relevance" not in phrase
    assert "clarity" not in phrase


def test_staged_generator_focus_reaches_stage_one_and_two():
    # Stage 1 (requirements) and stage 2 (questions) both carry the focus directive.
    fake = _FakeAnthropic(json.dumps([{"requirement": "stay grounded"}]))
    gen = StagedRubricGenerator(client=fake, focus=["reasoning"])
    assert "FOCUS AREAS" in gen._requirements_system()
    assert "FOCUS AREAS" in gen._stage2_system()
    assert "reasoning" in gen._stage2_system()
