"""The §5 two-step decomposition: requirements -> atomic questions, linked + grouped."""

from __future__ import annotations

import json
from types import SimpleNamespace

from aah.layer_a.rubric_gen import ClaudeRubricGenerator, StagedRubricGenerator


class _FakeClient:
    def __init__(self, payload):
        self._payload = payload
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **_kwargs):
        return SimpleNamespace(content=[SimpleNamespace(text=self._payload)])


def test_questions_sharing_a_requirement_are_linked_and_stored():
    # Two atomic checks under one requirement, one under another.
    items = [
        {"requirement_text": "report revenue", "dimension": "factual_consistency",
         "subtype": "number_error", "eval_method": "llm_judge",
         "question_text": "Does it state revenue was $4.2B?", "violation_example": "wrong",
         "must_pass": False},
        {"requirement_text": "report revenue", "dimension": "factual_consistency",
         "subtype": "number_error", "eval_method": "llm_judge",
         "question_text": "Does it state YoY growth was 8%?", "violation_example": "wrong",
         "must_pass": False},
        {"requirement_text": "report margin", "dimension": "factual_consistency",
         "subtype": "number_error", "eval_method": "llm_judge",
         "question_text": "Does it state margin was 21%?", "violation_example": "wrong",
         "must_pass": False},
    ]
    gen = ClaudeRubricGenerator(client=_FakeClient(json.dumps(items)))
    rubric = gen.build("summarize the results", context="...")

    assert len(rubric) == 3
    # requirement_text is stored on each atomic question.
    assert all(q.requirement_text for q in rubric)
    # Questions sharing a requirement share a requirement_id; different requirements differ.
    assert rubric[0].requirement_id == rubric[1].requirement_id
    assert rubric[2].requirement_id != rubric[0].requirement_id
    # Grouping by requirement yields 2 requirements over 3 atomic checks.
    assert len({q.requirement_id for q in rubric}) == 2


class _QueueClient:
    """Fake client that returns queued payloads in order and records each system prompt."""

    def __init__(self, payloads):
        self._payloads = list(payloads)
        self.systems: list[str] = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, *, system=None, **_kwargs):
        self.systems.append(system or "")
        return SimpleNamespace(content=[SimpleNamespace(text=self._payloads.pop(0))])


def test_staged_generator_uses_a_call_per_stage_with_distinct_skill_sets():
    # Stage 1 returns two requirements; stage 2 is called once per requirement.
    requirements = json.dumps([{"requirement": "report revenue"}, {"requirement": "report margin"}])
    q_for_revenue = json.dumps([
        {"dimension": "factual_consistency", "subtype": "number_error", "eval_method": "llm_judge",
         "question_text": "Does it state revenue was $4.2B?", "violation_example": "wrong",
         "must_pass": False},
    ])
    q_for_margin = json.dumps([
        {"dimension": "factual_consistency", "subtype": "number_error", "eval_method": "llm_judge",
         "question_text": "Does it state margin was 21%?", "violation_example": "wrong",
         "must_pass": False},
    ])
    client = _QueueClient([requirements, q_for_revenue, q_for_margin])

    gen = StagedRubricGenerator(client=client)
    rubric = gen.build("summarize results", context="revenue $4.2B, margin 21%")

    # One requirements call + one call per requirement = 3 calls.
    assert len(client.systems) == 3
    # Distinct skill sets: the first call is the analyst, later calls are the test designer.
    assert "REQUIREMENTS ANALYST" in client.systems[0]
    assert all("TEST DESIGNER" in s for s in client.systems[1:])
    # Two requirements -> two atomic questions, each linked to its parent requirement.
    assert len(rubric) == 2
    assert {q.requirement_text for q in rubric} == {"report revenue", "report margin"}
    assert len({q.requirement_id for q in rubric}) == 2
