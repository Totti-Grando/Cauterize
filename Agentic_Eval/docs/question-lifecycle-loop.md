# The question-lifecycle loop — one reference for the whole flow

This is the single map of the end-to-end evaluation loop: **question generation →
provider answer → evaluation → lessons / future question generation**. It points at the
real code (file · symbol) so you can reason about — and reshape — the whole loop from one
place. It is a reference, not a second implementation; the logic lives in the modules linked
below.

```
 seed + P_Q ──▶ [1] QUESTION GEN ──▶ question(str)
                                        │
                                        ▼
                                  [2] PROVIDER ──▶ response(str)
                                        │
                        question + response
                                        ▼
     [3] EVALUATION:  requirements ─▶ atomic binary questions ─▶ score each ─▶ aggregate
                                        │
                                        ▼
                                   AuditRecord
                                        │
                    (many records over seeds)
                                        ▼
     [4] LESSONS:  collect failures ─▶ generalize lessons ─▶ patch P_Q ─▶ (back to [1])
```

The four stages are wired together by `run_once(...)` (one pass = stages 1–3) and
`optimize(...)` (the outer loop = stage 4 re-running stages 1–3 with an evolving `P_Q`).

---

## [1] Question generation → `str`

- **Files:** `aah/layer_a/question_gen.py`, `aah/layer_a/seeds.py`, `aah/layer_a/attack_seeds.py`
- **Entry:** `ClaudeQuestionGenerator.generate(self, p_q: str, seed: str, mode: Mode) -> str`
- **Flow:** system prompt = `f"{p_q}\n\n{mode_instruction}"`, user = the seed → one
  `messages.create` → `_extract_text` → the question (Quality) or attack probe (Adversarial).
- **Seeds:** `seeds.py` (`FINANCE_SUMMARY_SEED`, `SUPPORT_FAQ_SEED`, `seed_to_text`);
  adversarial probes come from `attack_seeds.py` (`ATTACK_SEEDS`, `build_attack_rubric`).
- **Output:** `str question`.

> **Not wired yet (redesign targets):**
> - **Focus** does not reach this stage — today it steers the *rubric* generator only (see R6
>   in `rubric_gen.py`). To make "question generated from focus areas" real, focus must be
>   threaded into `generate(...)`.
> - **Personas / traits** are not built here at all — that is the **P-series** (persona/trait
>   order). When built, a persona+trait+focus *directive* shapes the question (generation-only;
>   the rubric generator and scorers never see it).

## [2] Provider answer → `str`

- **Files:** `aah/layer_a/providers/` — `base.py` (interface), `fixture.py`, `gemini.py`,
  `groq.py`, `http.py`.
- **Interface:** `ProviderAdapter.query(self, question: str) -> str` (`providers/base.py`).
- **Invoked in:** `run_once` (`pipeline.py`) — one query per run, concurrently with rubric build.
- **Output:** `str response` (the system-under-test's answer).

## [3] Evaluation → `AuditRecord`

- **File / entry:** `aah/layer_a/pipeline.py · run_once(...)`

  ```python
  async def run_once(*, seed, p_q, mode, generator, provider, rubric_gen, router,
                     config=None, context=None, prompt_version="P_Q@v0", iteration=0,
                     kept_question_ids=None, runs=1, evaluator=None, provider_info=None,
                     gating_router=None, gating_panel=None) -> AuditRecord
  ```

- **Ordered steps inside `run_once`:**
  1. `config = config or default_weight_config()` → `WeightConfig` (carries tiers, gating
     subtypes, focus, thresholds).
  2. `question = generator.generate(p_q, seed, mode)` — stage [1].
  3. Fork: `rubric_gen.build(question, ctx)` ∥ `runs ×` `provider.query(question)`, then join.
     - **Rubric build** (`rubric_gen.py · StagedRubricGenerator.build`): task → **Requirements**
       (stage-1 analyst call) → per requirement, **atomic BinaryQuestions** (stage-2 call), each
       born-tagged `{dimension, subtype, eval_method, must_pass, check_directive}`; §9 holistic
       cap applied. **This is the requirements → atomization step.**
  4. Gating top-up (F5): if the rubric has any CRITICAL check, query up to `gating_min_runs`.
  5. Score each question → `Verdict{score 0|1, explanation(required), evidence?}` via
     `router.py · RealEvaluatorRouter.score` → the scorer chosen by `eval_method`
     (`deterministic` / `nli` / `injection_detector` / `source_check` / `llm_judge`). CRITICAL
     checks may use a cross-family reference judge or a panel (F4).
  6. Multi-run combine (§9) + phi-dedup prune (`kept_after_phi_dedup`).
  7. **Aggregate:** `aggregator.py · aggregate(verdicts, rubric, config, kept, active_dimensions)`
     → `RunScore` (per-dimension mean → effective (tier × focus) weight → weighted overall;
     gates: CRITICAL threshold, `must_pass==0`, or a triggered **gating subtype**; coverage:
     every active dim reported, no-data dims **abstain**).
  8. Provenance (F1), yes-rate summary (F6), then emit.
- **Output:** `aah/contracts/models.py · AuditRecord` — `{mode, task, question, response,
  rubric, verdicts, scores, weight_config, provenance, focus, effective_weights, ...}`.

> **Where the scoring redesign lands:** which library/method scores each dimension is decided by
> `config/taxonomy.py · DIMENSION_EVAL_METHOD` (dimension → `eval_method`) and the scorer set
> wired in `router.py · default_router`. Moving dimensions from `llm_judge` to deterministic
> library scorers = edit that table + add scorers to the router. Atomization (step 3) is the
> mechanism that feeds the **completeness / coverage** signal; the requirements it enumerates are
> what "did the answer cover everything" is measured against (cf. Layer C `layer_c/omission.py`,
> source-recall + seeded-catch). Every scorer must still return `{score, explanation, evidence?}`.

## [4] Lessons / future question generation → evolved `P_Q`

- **File / entry:** `aah/layer_b/orchestrator.py · optimize(...)`

  ```python
  async def optimize(*, initial_p_q, run_layer_a, notetaker, updater, mode=Mode.QUALITY,
                     max_iterations=5, budget=2000, reference_overall=None, epsilon=0.02,
                     collect=None, objective_fn=None) -> OptimizationResult
  ```

- **Per-iteration flow:**
  1. `records = await run_layer_a(p_q, i)` — runs stages [1]–[3] over the seed(s).
  2. Collect failures: `failure_signals.py · collect_failures(records)` (verdicts with
     `score==0` / `attack_success`) → `list[Failure]`. (Rubric-quality mode swaps in
     `rubric_critic.py · critic_collector`.)
  3. Objective: quality → mean overall; adversarial → failure count.
  4. Generalize: `notetaker.py · NoteTaker.take_notes(failures, mode)` → `list[Lesson]`
     (`PROMPTABLE` | `STRUCTURAL`); `lessons.py · dedup_and_prune`.
  5. Patch the meta-prompt: `updater.py · Updater.patch(p_q, promptable, budget)` → new `P_Q`
     (with `enforce_budget`). This **evolved `P_Q` feeds the next round's stage [1]** — the
     "future question generation" link.
  6. Convergence checks (no-new-signal / reference-match / no-promptable-lessons / prompt-stable).
- **Output:** `aah/layer_b/loop_results.py · OptimizationResult` (best/final `P_Q`, per-iteration
  records, structural findings).

> Note: today the loop evolves the **`P_Q` meta-prompt** (question generation) and, in the
> rubric-quality variant, the rubric-generator **guidance**. It does not yet evolve persona/trait
> selection — that composes in once the P-series exists.

---

## Top-level entry points (where all four stages are wired)

| Entry | File · symbol | What it runs |
|---|---|---|
| CLI quality demo | `cli.py · _run` | one `run_once` over a seed |
| CLI adversarial | `cli.py · _run_adversarial` | `build_attack_rubric` + `run_once` |
| CLI Layer B loop | `cli.py · _run_loop` | `optimize(...)` |
| CLI live (real LLMs) | `cli.py · _run_live` | full `run_once` with Claude generator + staged rubric + real router |
| CLI rubric learning | `cli.py · _run_learn` | `optimize` + `RubricCritic` + `critic_collector` |
| API single turn | `api/live_engine.py · stream_eval → _stream_job` | generate → query → evaluate → collect lessons, streamed |
| API auto loop | `api/live_engine.py · stream_run_loop` | N rounds fed by accumulated lessons |

## Data objects that flow (all in `aah/contracts/`)

`Seed/str` → `str question` → `str response` → `BinaryQuestion[]` (rubric) → `Verdict[]`
→ `RunScore` → `AuditRecord` → `Failure[]` → `Lesson[]` → evolved `P_Q` → (loop).
