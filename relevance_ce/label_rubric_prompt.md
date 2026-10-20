# Labeling prompt — real (question, claim) pairs

Use with Claude (or another strong LLM) to label pairs pulled from your pipeline. Send one
question with all of its candidate claims in a single call: the labeler is more consistent when
it sees the full set, and it costs less. Ask for JSON back.

Run a second, independent pass on a 10% sample with a different model or a reordered claim list,
and send every disagreement to human adjudication. Target ≥ 85% agreement between passes before
you trust a batch.

---

## System prompt

You label how relevant each short claim is to a question. You are given the question, the
claims, and tags from an entity-extraction system. Tags can be wrong: when the text and a tag
disagree, follow the text.

Apply these checks in order. The first one that matches is the label.

1. **IRRELEVANT** — no shared entity, topic or ecosystem with the question.
2. **UNRESOLVED** — the claim refers to something that could be the question's entity, but the
   reference can't be pinned down from the claim alone ("the firm", "the bank", "a large
   Canadian manager", "this spring" when the period matters).
3. **ECOSYSTEM** — the claim's main entity is adjacent to the question's: a competitor, parent,
   subsidiary, regulator, distributor or platform.
4. **WRONG_RELATION** — the same entities appear, but the relationship is a different type, or
   its direction is reversed (A acquired B vs B acquired A).
5. **WRONG_INTENT** — same entity, but a different attribute or question type (fees when the
   question asks about flows).
6. **WRONG_TIME** — same entity and attribute, but the period falls outside the question's
   temporal scope. Scope comes from the question: "since 2023" includes 2024.
7. **DIRECT** — the claim supplies the answer as asked.
8. **PARTIAL** — the claim supplies part of the answer: a subset (one product line, one
   segment), one component, a sub-period, or a bound.
9. **CONTEXT** — on the question's topic and within its scope (e.g. same period), frames the
   answer but supplies none of it (industry-wide figures, background).

Do not judge whether a claim is true. Judge only what it would contribute to answering the
question if it were true.

## User message template

```
QUESTION: {question}
QUESTION TAGS: {q_tags}

CLAIMS:
1. {claim_1}  || {c_tags_1}
2. {claim_2}  || {c_tags_2}
...

Return JSON only:
[{"id": 1, "label": "<ONE OF THE 9 LABELS>", "confidence": <0-1>, "reason": "<= 12 words"}, ...]
```

## Turning the output into training rows

Write each labeled pair as one JSONL row:

```json
{"qid": "real-000123", "question": "...", "q_tags": "...", "claim": "...", "c_tags": "...",
 "label": "PARTIAL", "split": "train", "weight": 1.0, "source": "llm_v1"}
```

- `split`: assign by your primary entity id (hash → 80/10/10), never by row.
- `weight`: 1.0 for labels both passes agree on or a human adjudicated; 0.5 for single-pass
  labels with confidence < 0.7; drop anything below 0.4 confidence.
- Keep every reason string in a side file. They are the fastest way to audit a confusing class.
