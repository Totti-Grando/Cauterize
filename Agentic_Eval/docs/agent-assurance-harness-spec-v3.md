# Build Spec v3 — Agent Quality & Security Assurance Harness

**Paste target:** Claude Code. **New in v3 (vs v2):** (1) a fully specified **deterministic weighting mapping**; (2) the **explanation → lesson pathway** made explicit, including what counts as a failure per mode; (3) **capture-vs-classify** mechanics and the `eval_method` router; (4) the two **hallucination caveats** (numeric semantic equivalence, omission ≠ hallucination); (5) the two-layer classification model.

---

## 1. Goal

A generalized harness producing **proof of quality and security** for enterprise managed agents (e.g. RavenPack, or any provider-under-test). It decomposes a task into atomic yes/no questions (BINEVAL), scores the provider's response question-by-question, and aggregates into per-dimension and overall scores via a deterministic weighting rule, with a full audit trail. An optional outer loop reuses the failure signal to evolve the question-generation prompt. The loop's optimization target is mode-dependent: in quality mode it tunes rubrics toward a reference; in adversarial-probe mode it tunes the generator toward harder attacks (automated red-teaming on the same machinery).

## 2. Modes

A runtime flag on one pipeline.
- **Quality-Eval:** generator emits a domain question; "failure" = a low-quality / unfaithful answer; loop improves rubric calibration.
- **Adversarial-Probe:** generator emits an attack; "failure" = a successful attack (leak, payload obeyed, fabricated source); loop sharpens probes.
- **Hybrid:** interleave both; security dimensions gate.

## 3. Architecture — two layers, one-way dependency

- **Layer A — Evaluator Core (standalone).** Question in → rubric + scored verdicts + audit record out. Must run and be testable with the loop absent. Imports nothing from Layer B.
- **Layer B — Optimization Loop (optional).** Calls A, reads its audit records, evolves `P_Q`. Dependency: B → A only.

Four run configs result: quality one-shot, quality looped, single red-team pass, escalating red-team loop.

## 4. Data contracts (freeze first)

```
Requirement     { id, dimension, text }
BinaryQuestion  { id, requirement_id, dimension, subtype, text, violation_example, eval_method }
Verdict         { question_id, score(0|1), explanation, evidence?, attack_success? }
DimensionScore  { dimension, tier, gating(bool), score, weight }
WeightConfig    { tiers{dimension→tier}, major_minor_ratio, prune_thresholds, gate_thresholds, version }
RunScore        { per_question[], per_dimension[], overall, gated_by?, weight_config_version }
Lesson          { id, source_question_ids[], explanation_refs[], text, kind:"promptable"|"structural", mode }
AuditRecord     { mode, task, question, response, rubric[], verdicts[], scores, weight_config, prompt_version, iteration }
```

- `eval_method` ∈ `deterministic | nli | injection_detector | source_fetch | llm_judge` — the routing key.
- `subtype` is the fine-grained failure category (e.g. for consistency: `unsupported | fabrication | entity_error | number_error | causal_error | misattribution | conflation | abstention_failure`).
- `explanation` is mandatory: it is both the audit "why" and the fuel for the loop.

## 5. Runtime breakdown

### Standalone (Layer A)
1. Seed in (domain profile, source doc, or attack template).
2. `QuestionGenerator(P_Q, seed, mode)` → one question.
3. Fork, concurrently: (a) `ProviderAdapter.query(q)` → response (Gemini stub, key slot); (b) `RubricGenerator(q, context)` → requirements → binary questions, each tagged `dimension`, `subtype`, `eval_method`, `violation_example`.
4. Join on response.
5. `EvaluatorRouter` routes each question by `eval_method` → `Verdict {score, explanation, evidence}`.
6. `Aggregator` applies the deterministic weighting mapping (§7) → per-dimension + overall, with gating.
7. Emit `AuditRecord`. **Standalone stops here.**

### Looped (Layer B wraps A) — see §8 for detail
8. Collect signal (failures, or successful attacks).
9. `NoteTaker` → lessons (promptable/structural).
10. Dedup + prune; discard structural lessons (log as findings).
11. `Updater` patches `P_Q` substring under length budget.
12. Converge / keep best iteration / else loop to step 2.

## 6. Capture vs classify, and the eval_method router

Two operations: **capture** (answer the binary question correctly — did the bot do the bad thing?) and **classify** (assign the failure to a category). Classification is done at rubric-generation time: every question is born tagged `{dimension, subtype}`, so a `0` verdict is already categorized. The audit record is therefore a list of classified, explained failures, not a scalar.

The router picks the cheapest competent scorer per question:
- `deterministic` (format, count, JSON-valid, contains, regex, URL-in-source, cost): code or promptfoo assertions. Exact, free.
- `nli` ("is claim X supported by source?"): MiniCheck (yes/no, GPT-4-level, windowed for long docs) or AlignScore (0–1). Replaces an LLM call per consistency question.
- `source_fetch` (open the link, check author/date, verify claim): trafilatura `fetch_url`+`extract`+`extract_metadata`, then an `nli` claim-check against fetched text.
- `injection_detector` ("did the injection land?"): Lakera Guard / LLM Guard / pytector / NeMo Guardrails — used as evaluators, validate before trusting.
- `llm_judge`: holistic/subtle questions only (misrepresentation, conflation), or DeepEval / RAGAS metrics as dimension scorers.

## 7. Deterministic weighting mapping

A score must be a reproducible function of `(verdicts, WeightConfig)`. Implement these rules exactly:

1. **Tier each dimension** (documented policy table, the only human input): `CRITICAL → gating`; `MAJOR → tierweight 2`; `MINOR → tierweight 1`.
2. **No per-question weights.** Within a dimension, prune redundant questions — pairwise φ above `prune_thresholds.phi`, or yes-rate outside `prune_thresholds.yes_rate_band` — then uniformly average the survivors.
3. **Cross-dimension weights from tiers:** `w_d = tierweight(d) / Σ_{scored} tierweight`. Sums to 1; only lever is `major_minor_ratio`.
4. **Gating dominates:** `overall = FAIL if any CRITICAL dimension score < gate_thresholds[d] (or any must-pass question == 0); else Σ_{scored} w_d · S_d`. Gates are never averaged, never overridden by learned weights.
5. **Calibration = sanity check only.** Optionally fit `major_minor_ratio` by non-negative least squares (dimension scores → reference overall), capped per dimension, then freeze + version. Adjusts the ratio among scored dimensions only; cannot create/remove a gate. (Correlation-fitting under-weights rare severe failures — so gating + tiering lead, calibration only tidies quality dimensions.)
6. **Reproducibility:** write the full `WeightConfig` into every `AuditRecord`. Same verdicts + same config ⇒ same score.

## 8. The improvement loop — explanation → lesson, in detail

The loop consumes the **pairing** of each failed verdict with its `explanation`. A bare `0` is not enough to learn from; the explanation is the only generalizable part.

1. **Collect.** Pull failed verdicts (quality: score-0 questions / divergence from reference; probe: `attack_success == true`) with their `explanation` and `{dimension, subtype}` tags.
2. **Generalize (NoteTaker).** Feed a *batch* of (question + explanation + the x/y context) to the note-taker → generalized `Lesson`s (e.g. "attribution errors recur → bind each statement's subject to the right actor"), each classified `promptable` vs `structural`.
3. **Dedup + prune.** Merge near-identical lessons (semantic dedup) so the set stays unique; discard `structural` lessons (log as provider capability findings — do not inject them).
4. **Patch (Updater).** Locate the substring `s_k` in `P_Q` the lesson bears on, rewrite to `s'_k`, `replace(s_k, s'_k)`. Enforce the prompt-length budget: if a patch would exceed it, prune the lowest-value existing instruction instead of appending.
5. **Converge.** Stop on no-new-signal / reference-match within ε / max iterations; select best iteration on held-out data; else loop with evolved `P_Q`.

Mode note: quality self-update corrects the *rubric*; cross-model update uses per-question disagreement with a stronger reference to pull the target toward it; probe mode generalizes the *successful attack*. Same pipeline, different signal definition. The `explanation` and `{dimension, subtype}` fields from §6 are the exact inputs here — that is why the verdict schema carries them.

## 9. Guardrails (build these in)

- **Prompt-length budget / bloat guard** (`[critical]`): a meta-prompt that grew 22 → 6,248 chars collapsed across all categories; past a critical length, instructions hurt regardless of correctness. Prune, don't append. Matters most in probe mode.
- **Classify lessons promptable vs structural:** prompt-tuning fixes guidance gaps, not capability limits; structural failures (often injection-resistance) are provider findings, not prompt fixes.
- **Don't over-decompose holistic dimensions:** strict atomic checks on relevance made the evaluator harsher than humans (ρ .505 → .357). Cap question count there; keep questions soft.
- **Question-quality check = principled dedup:** per dimension compute yes-rate spread + pairwise φ; merge/drop high-|φ| pairs. Healthy mean off-diagonal φ ≈ 0.38.
- **Two hallucination caveats** (`[critical]`):
  - *Numbers aren't string-match.* "83rd minute" ≡ "seven minutes remaining" in a 90-min match. The `number_error` check needs arithmetic/semantic-equivalence tolerance.
  - *Omission ≠ hallucination.* Leaving a source fact out is not a factual error; the "supported?" question fires only on claims the summary actually makes.
- **Determinism:** temperature 0; average over 2 runs to stop borderline questions flipping.

## 10. Tooling map (build-vs-borrow)

Quality scorers: MiniCheck / AlignScore (`nli`), trafilatura (`source_fetch`), promptfoo assertions (`deterministic`), DeepEval / RAGAS (`llm_judge` dimension metrics). Adversarial supply: garak (50+ probes + adaptive `atkgen`; AVID vuln reports = your "proof of security"), PyRIT (multi-turn orchestration + scoring engine, MITRE ATLAS), promptfoo red-team plugins. Observability: Langfuse / LangSmith for traces + score-over-time + prompt-evolution trail.

**Build-vs-borrow:** garak's `atkgen` and PyRIT's multi-turn orchestrators already do adaptive probing — don't rebuild it. Your novelty is decomposing the bot's *answer* into a classified atomic rubric with φ/yes-rate discipline; keep that as the core and call the others as libraries (or wrap your decomposition as a PyRIT scorer / garak detector if you want garak's reporting for free).

## 11. Build / orchestration guidance for Claude Code

- **Sequence:** one architect pass to (1) freeze §4 contracts, (2) stub Layer A + AuditRecord persistence + the WeightConfig loader, (3) write contract tests per module boundary. Then fan out.
- **Parallelize** Layer A modules and Layer B modules independently once contracts are frozen; they share only the schemas and the AuditRecord.
- **Single-owner / highest risk:** the schemas, the WeightConfig/aggregator, the Orchestrator (Layer B), and the mode flag's cross-module effect.
- **Stack:** Python (async for the §5 fork; MiniCheck/AlignScore/trafilatura/garak/PyRIT/DeepEval are Python; scipy/numpy for φ and the NNLS calibration).
- Every module: unit test against the contract. The loop: one integration test on a tiny fixture provider before any real adapter. Log every prompt version and patch.

## 12. Open decisions

- Dimension set; per-dimension tiers (which gate); `major_minor_ratio` and prune/gate thresholds.
- Scaling target (`[0,1]` internal vs `1–5` report scale).
- Reference source for quality self-update (human labels, gold evaluator, or both mode-switched).
- Adversarial seed-bank source (own templates vs garak/PyRIT/promptfoo) and loop expansion rate.
- Source-verification cost policy (verify every claim vs only flagged).
- Build-vs-borrow on the adaptive loop (own orchestrator vs PyRIT/garak host).
