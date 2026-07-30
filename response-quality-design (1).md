# Response Quality — build spec (v6)

Four dimensions — **accuracy, completeness, relevance, task_success** — one section each, build broken into numbered sub-components. Rule throughout: **AI extracts and judges yes/no; code computes every number.** Inline links point to the source for each method; the full list is at the bottom.

---

## 0. Build once — shared claim-extraction pipeline

Accuracy, completeness, and relevance all consume the answer's atomic claims, so build and cache this first.

1. **Segment** the answer into sentences — spaCy `[T1]`; deterministic, gives the unit for the next step.
2. **Select verifiable spans** `[T3-gen]`. FactScore/SAFE extract *everything* and so unfairly punish opinions/hedges/hypotheticals; [VeriScore](https://aclanthology.org/2024.findings-emnlp.552/) (Song et al., EMNLP 2024) fixed this — keep only spans that "can plausibly be proven true or false"; route unverifiable spans to `uncertainty_handling`/`actionability`, never to truth scoring.
3. **Extract atomic claims** with **Claimify's** (Metropolitansky & Larson, 2025) three steps — **selection** (sentences with verifiable content) → **disambiguation** (resolve ambiguity; *flag*, don't guess, when context can't) → **extraction** (one proposition per claim). Avoids FactScore's run-together/ambiguous subclaims.
4. **Decontextualize** each claim `[T2 coreferee + T3-gen]`. A claim read out of context ("His notable credits include The Game") is unverifiable; resolve every pronoun/referent and — per **Molecular Facts** (Gunjal & Durrett, 2024) and [DnDScore](https://aclanthology.org/2025.emnlp-main.1205.pdf) (EMNLP 2025) — carry the decontextualizing context forward so the verifier sees it.
5. **Pin & measure stability.** Factual-precision pipelines are **provably sensitive to the decomposition method** (Wanner et al., 2024), so pin the extractor model + prompt + granularity, version the claim set, and measure whether re-runs yield the same claims — the biggest reproducibility risk in the category.

*Output:* a cached set of atomic, decontextualized, verifiable claims, each with a source-sentence pointer and any citation.

*Read before §1/§3/§4 — three axes, two dimensions:* **on-topic** and **responsiveness** (answers the *specific* ask) both live in **relevance**; accuracy imports responsiveness as its false-positive guard. **Goal accomplishment** is separate and lives in **task_success**. They dissociate (relevant-but-unsuccessful; true-but-off-ask) and only look identical on trivial factual asks.

---

## 0.5 Contracts, records & audit

One shared data shape makes every dimension interchangeable, replayable, and auditable — this is where determinism becomes verifiable rather than asserted.

1. **Claim object** (cached from §0): `{id, text, source_sentence, verifiable, decontextualized, citation?, extractor_version}`.
2. **Atom record** — the audit primitive, one per yes/no check: `{question, tier, verdict∈{0,1}, evidence (span / source-id / score), grader_id, model+version, seed?, timestamp}`. Every boolean is stamped with *what decided it and why*, so any verdict is inspectable and, for T3, challengeable.
3. **Dimension result**: `{dimension, score∈[0,1], band, CI, n, inputs_hash, atom_ids[], formula_id, abstained}`.
4. **Replay guarantee** — the score must be **recomputable from the logged atoms + formula without re-invoking a model**: T1/T2 atoms replay bit-for-bit; a T3 atom replays from its logged verdict (its model+version is stamped so drift is *detectable*, not silent). If re-running `formula_id` over `atom_ids` doesn't reproduce `score`, that's a defect, not noise.
5. **Reproducibility fence** — every generated reference (claim / requirement / unit / outcome set) carries `version + corpus_hash + pinned_model`; certification runs use pinned references, discovery regenerates; any sampling step (paraphrase, RAGAS reverse-questions) carries a fixed `seed`.

*Inputs each dimension needs:* accuracy → answer + retrieved context + citations · completeness → question + sources + fixed requirement templates · relevance → question + answer · task_success → question + answer.

---

## 1. accuracy — MAJOR · derived

Not an independent scorer — computed over the cached claims by running four booleans each, then composing in code.

1. **grounded?** `[T2]` — is the claim entailed by the retrieved context. An entailment check, not similarity; mirrors [RAGAS faithfulness](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/) (`|supported|/|total|`). Verifier is a **fixed model** — [Bedrock contextual-grounding](https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-components.html), [fairseq RoBERTa-MNLI](https://pytorch.org/hub/pytorch_fairseq_roberta/) (torch.hub, non-HF), or a **MiniCheck** (Tang et al., 2024) / [HHEM](https://www.vectara.com/blog/evaluating-rag)-style checker — never a generative judge.
2. **source-adequate?** `[T1/T2]` — imported from `source_quality`; a claim grounded in a bad source must not count.
3. **attributed?** `[T2 directional NLI]` — imported from `source_attribution`; does the *cited* chunk entail this claim (catches right-fact/wrong-citation).
4. **responsive?** `[T2]` — imported from `relevance` (§3); does this true claim bear on the specific ask. The false-positive guard; accuracy does **not** recompute it.
5. **Compose** `[code]`: `claim_correct = 1 ∧ 2 ∧ 3 ∧ 4` (conjunction — each is necessary), then `accuracy = Σ correct·w / Σ w`.
6. **Residual (Tier-3 residue):** **unsourced claims** (nothing to ground against) → reference check or truth-judge `[T3]`; **inferred claims** (entailed by no single chunk) → the **inference-validity** check shared with `logical_consistency` (computed once, read by both).
7. **Importance-weight** `w` with the vital/okay nugget labels from §2 — not all claims matter equally ([importance-sensitive factuality](https://arxiv.org/pdf/2510.07083), 2025); a false *vital* claim costs more. Toggle; off = uniform.

*Profile:* Nexa (trusted corpus) → source-adequacy ≈ 1, residue ≈ 0 → **accuracy ≈ groundedness**; RavenPack → all terms live. *Edges:* exact-match numeric claims (not NLI — "$1.2B" vs "$1.3B" must fail), bind temporal claims to as-of date, never fall back to cosine (misses negation).
**Tools:** Bedrock grounding / fairseq-NLI · directional NLI · source_quality + relevance imports · judge (residual) · `numpy`. **Confirm:** verifier; weighting on/off; residual policy per profile; numeric tolerance.

---

## 2. completeness — MAJOR · two-tier nugget recall

False-**negative** axis — of what a good answer should contain, how much is present. Built as **two tiers** to split evaluator trust: a **requirement tier** (fixed scaffold, no AI recall risk on the coverage axis) and, under each requirement, **atomic entailment-decidable binary units** (the nuggets). This is the current research frontier — [HD-Eval](https://arxiv.org/pdf/2606.08625) (Sun & Zhang, ACL 2024) aligns evaluators through **hierarchical criteria decomposition**; [Qworld](https://www.alphaxiv.org/overview/2603.23522) (Gao et al., 2026) recursively expands a question into a **tree of binary criteria, every leaf an unambiguous judgment**; [ExpertLongBench](https://arxiv.org/pdf/2606.08625) (Ruan et al., 2025) runs long-form eval as **rubric → checklist → comparison**; and [question-specific rubrics beat generic ones](https://dl.acm.org/doi/10.1145/3702652.3744220) (Pathak et al., 2025; [RubricRAG](https://www.emergentmind.com/topics/llm-generated-rubrics), 2026). Scoring stays **strict vital nugget recall** (Voorhees 2003; [AutoNuggetizer](https://dl.acm.org/doi/10.1145/3726302.3730090), Pradeep et al. SIGIR 2025, validated at **τ = 0.87 vs human** — the bar to clear).

1. **Tier-1 requirements** `[structural oracle]` — decompose the question into the facets a complete answer must cover ("cost drivers, pricing actions, one-time items, FX"). **Fix this tier wherever possible** — templated by question-type or human-approved once (as [CheckEval](https://aclanthology.org/2025.emnlp-industry.136.pdf), Lee et al. 2024, uses a human-defined taxonomy the LLM only populates). *This is where the risk actually splits:* the coverage guarantee rests on a fixed, reviewable scaffold, not an AI recall step. Hierarchy alone doesn't reduce trust — *fixing the top tier* does.
2. **Tier-2 units** `[T3-gen]` — within each requirement, generate atomic units covering its subspace, top-down (from the requirement) + bottom-up (from the sources, catching drop-from-source omission; heavier for RavenPack). Each unit is one nugget — Qworld's "leaf" — phrased as a checkable statement (or Q/A pair; scores identically).
3. **Unit admissibility gate** `[T1 + T2 + T3-once]` — a unit enters the frozen set only if it passes three checks, guarding against the **evaluator over-acceptance** failure mode ([LEGIT](https://www.emergentmind.com/topics/llm-generated-rubrics)): **atomic** (one proposition — parse/conjunction-split `[T1]`), **self-contained** (decontextualized, coref-resolved `[T2+T1]`, reusing §0), **entailment-decidable against the answer** (checkable from the answer text alone, no external knowledge — a one-time admission pass `[T3]`; units needing world-knowledge belong to accuracy, not completeness). Reject/repair failures, then **freeze** the vetted set. This is what keeps every Tier-2 unit genuinely T2-answerable — not prompt-hope, but a construction-time gate.
4. **Merge/dedupe** `[T2 Titan + code]` — cluster near-duplicate units across the top-down/bottom-up passes.
5. **Label vital / okay** per unit *and* per requirement `[T3]` — [RAGCHECKER](https://aclanthology.org/2025.emnlp-industry.136.pdf) shows flat importance misses task-specific hierarchies, so materiality is carried at both tiers; reuse for accuracy's weighting.
6. **Assign** `[T2 NLI]` — per unit, one binary: is it *fully* supported by the answer (bidirectional entailment; answer = premise, unit = hypothesis; partial = unsupported). **ARGUE's** (Mayfield et al., 2025) binary-judgment structure; credits paraphrase, which string-match can't.
7. **Score, two levels** `[code]`: **per-requirement recall** = supported units / that requirement's units (**normalize per requirement** so a 10-unit facet doesn't drown a 2-unit one); **requirement coverage** = requirements with ≥1 supported unit / total (a sharp materiality signal — a whole facet missing). `completeness = vital-weighted mean of per-requirement recall`; report requirement-coverage alongside. Core metric remains **strict vital recall** ([TREC 2025 RAG](https://arxiv.org/pdf/2603.09891)).
8. **Bound + reproduce** `[scipy]` — **Wilson 95% CI**; **abstain when < ~10 vital units**; version the requirement templates + unit set to question + corpus hash; pin; **τ ≈ 0.87 is the answerability meter** (if units stop being cleanly answerable, assignment–human agreement drops); certification-suite only. The unknown-unknown a fixed Tier-1 still misses → the human recall sample with its CI.

**Determinism/audit note:** Tier-1 is a fixed scaffold (deterministic coverage), the admissibility gate is mostly `[T1/T2]`, assignment is `[T2]` reproducible, all scoring is code — the only AI *generation* is Tier-2 unit drafting, which is gated, frozen, and τ-validated. **Tools:** judge (units + labels) · fairseq-NLI / Bedrock grounding (assign) · Titan (dedupe) · spaCy/`coreferee` (admissibility) · `scipy` (CI). **Confirm:** which question-types get fixed vs generated Tier-1; strict-vital vs weighted; min-n; per-requirement normalization; validation cadence.

---

## 3. relevance — MAJOR · on-topic + responsiveness

Fit to the **question** — on-topic + responsive — and it *owns* the responsiveness signal accuracy imports. Two reproducible methods (pick or combine); **T2-primary, not T3**, because both give a number without a generative verdict on the score.

1. **Method A — [RAGAS answer-relevancy](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/answer_relevance/)** `[T3-gen question step + T2 cosine]`: generate N (default 3) questions *from the answer*, embed them + the original with **Bedrock Titan**, score `AR = (1/N) Σ cos(E_gi, E_o)`. Penalizes incomplete/unfocused answers; measures intent-match, not accuracy. The **number is deterministic cosine** — AI doesn't compute it. *RAGAS is usable:* pure-Python framework, no bundled models — point its LLM at Bedrock Claude and embeddings at Titan, nothing touches Hugging Face; pin the reverse-question model and treat as diagnostic, not gate.
2. **Method B — [Bedrock contextual-grounding relevance](https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-components.html)** `[T2]`: a fixed query↔response relevance score from `ApplyGuardrail`, thresholded in code — no generation step, the deterministic-first **default**.
3. **Answer-level checks** `[T2]`: response-relevant-to-query (A or B ≥ τ) and addresses-the-specific-ask.
4. **Claim-level responsive atom** `[T2]`: per claim on-topic ∧ on-ask — **this boolean is what accuracy imports**, computed once here.
5. **Combine** `[code]`: `mean(on-topic ∧ on-ask)` with an **off-ask cap** — missing the specific ask caps the score regardless of on-topic volume.
6. **Abstention** — per **"Knowing When You Don't Know"** (Thakur et al., EMNLP 2024): on an unanswerable/out-of-scope question a proper decline scores relevant; a confident off-topic answer doesn't.
7. **Residual** `[T3-res]` — judge only the subtle "on-topic but answers a *different sub-question*" cases both scores miss.

*Edges:* over-answering (off-ask cap + conciseness ding, not a zero); multi-part (score per part, aggregate). **Tools:** Bedrock grounding-relevance (B) or RAGAS-on-Bedrock + Titan (A) · judge (residual). **Confirm:** A vs B vs both; τ; per-claim atom via grounding-relevance vs light NLI.

---
## 4. task_success - Major · Goal Accomplishment

## 4. task_success — MAJOR · verifier-routed (goal accomplishment)

Whether the user's **objective** would actually be achieved — fit to *goal*, not question ("fix this code" answered with a correct explanation and no fix = accurate + relevant + task **failure**). **Not irreducibly T3.** The objective decomposes into required outcomes, and each outcome routes to the cheapest verifier that fits — the agent-eval literature's standard is a **deterministic oracle, with the judge as the fallback** for the residue state and rules can't capture: goal achievement is "typically verified by a deterministic oracle — database state, file-system state, or test-case execution" ([Hitchhiker's Guide to Agentic AI](https://arxiv.org/pdf/2606.24937), 2026); an **execution evaluator** checks goal conditions after running the plan, with a **semantic evaluator** only where state can't capture the outcome ([SafeAgentBench](https://arxiv.org/pdf/2412.13178), 2024); environment-level scoring uses **hash-based terminal-state matching** ([Unified Framework](https://arxiv.org/pdf/2605.27898), 2026, following τ-bench); success validation "is often rule-based" ([Generalizability survey](https://arxiv.org/pdf/2509.16330), 2025); multi-step tasks are scored by **subgoal decomposition + sum**, SWE-bench-style ([KDD 2025 tutorial](https://sap-samples.github.io/llm-agents-eval-tutorial/2025_KDD_Evaluation_and_Benchmarking_of_LLM_Agents.pdf)). So: **deterministic fraction near-total for executable/structured/constrained tasks, shrinking to a small adequacy residue for open-ended goals.**

1. **Infer the objective** `[T3-gen]` — the intent, not the literal words ("why is this slow?" usually implies *and how to fix it*).
2. **Classify task type + pull a verifier-typed outcome template** `[T3]`. Each outcome in the template is **tagged with its verifier** (see the routing table). Templates are **human-authored and pinned** — per **Konstantinou et al. (ICST 2025)**, LLM-written assertions encode the *current, possibly buggy* behaviour rather than the intended one, so outcome checks are human-validated, never agent-authored, for the certification set (a structural oracle, like completeness's Tier-1).
3. **Decompose into concrete required outcomes** `[T3-gen]` — instantiate the template against this instance's specifics.
4. **Route each outcome to its tagged verifier** — `[T1]` presence/execution/state/constraint · `[T2]` coverage/import · `[T3]` adequacy only. **The judge fires only on `adequacy` outcomes**, which for executable/structured task types is often zero. Routing table:

   | Outcome type | Verifier | Tier | Example |
   |---|---|---|---|
   | artifact-presence | parse/structure check | `[T1]` | "a corrected code block exists", "a table is present" |
   | executable / test | run it — sandbox exec, unit test, linter, recompute | `[T1]` | "the fix runs", "the SQL returns the right rows", "the number is correct" (SWE-bench-style) |
   | state / end-condition | compare terminal state to ground truth (hash/state match) | `[T1]` | "the record was created", "the file has the expected contents" (τ-bench-style) |
   | constraint-satisfaction | reuse `constraint_compliance` | `[T1]` | "meets length/format", "includes X, excludes Y" |
   | coverage | reuse completeness's nugget-recall vs a task requirement set | `[T2 NLI]` | "covers both sides", "explains the mechanism's key steps" |
   | grounded / responsive | import from accuracy / relevance | `[import]` | "the recommendation is justified", "answers the specific ask" |
   | adequacy (residue) | judge — per-outcome binary | `[T3]` | "addresses the *root* cause", "at the *right* level", "the recommendation is *sound*" |

5. **Compute** `[code]`: `task_success = Σ achieved·w / Σ w` over required outcomes (graded/partial-credit `TSR_graded`).

*Reproducibility:* pin the task-type taxonomy + per-outcome verifier tags. *Edges:* multi-goal (decompose each, weight by primacy); implicit goals (step 1 must surface them); partial (the ratio captures it); impossible task (well-scoped "can't be done because X" = success, like relevance's abstention). *Determinism:* for code/SQL/numeric/structured/agentic tasks the dimension is effectively `[T1]` (execution + state + constraint checks that replay bit-for-bit and are more trustworthy than a judge's opinion of whether code runs); the `[T3]` residue is confined to adequacy on non-executable goals, and even there it's a per-outcome boolean with code aggregating. Every outcome's verifier tag + result is an AtomRecord (§0.5).
**Tools:** T1 parse/exec/state/constraint checks · completeness NLI (coverage) · accuracy/relevance imports · judge (adequacy only) · `numpy`. **Confirm:** task-type taxonomy + per-outcome verifier tags; execution sandbox in scope? (big determinism win for code/SQL); adequacy-outcome weighting.

---

## Category notes

Build §0 first (accuracy/completeness/relevance consume it), then completeness's units (which also supply accuracy's importance weights). Responsiveness is computed once in relevance, imported by accuracy, ignored by task_success. All four are **MAJOR**; the only gate touching the category is accuracy's **fabricated-citation** subtype (lives in `hallucination`). Honest Tier-3 surface after this design: the `[T3-gen]` decomposition steps, task_success's per-outcome verdicts, accuracy's unsourced/inferred residual, and the thin relevance residual — everything else (grounding, attribution, unit-support, relevance scoring, all recall/precision/composition) is T2 + code. Every generated reference (claim/unit/outcome set) is pinned + human-sample-validated (τ ≈ 0.87) and lives in the certification suite; discovery regenerates freely.

**Development summary — I/O, output, and exactly how each tier is used** (bands are policy-set; default G ≥ 0.90 / A ≥ 0.75 / R < 0.75). **T1** = deterministic code (rules, parsers, execution, set-membership, all arithmetic) — replays bit-for-bit. **T2** = fixed model (NLI / grounding / embeddings), score thresholded to a boolean *in code* — replays deterministically. **T3** = generative model: **T3-gen** builds a *pinned, frozen, τ-validated* reference (extraction, nuggetization, templates); **T3** (judge) emits a single yes/no on a residual atom — the only non-replayable step, stamped with model+version.

| Dimension | Inputs | Output | T1 — deterministic code | T2 — fixed model (thresholded in code) | T3 — generative |
|---|---|---|---|---|---|
| accuracy | answer + context + citations | `[0,1]` = correct/verifiable-claims + band | conjunction + weighted mean; numeric/temporal exact-match; citation set-membership | grounded, attributed (NLI/grounding); source-adequacy import | **gen:** claim extraction/decontext · **judge:** unsourced/inferred residual only |
| completeness | question + sources + requirement templates | strict-vital-recall + requirement-coverage + Wilson CI | Tier-1 scaffold; admissibility (atomicity); all recall/coverage/CI math | unit assignment + dedupe (NLI/embeddings) | **gen:** Tier-2 unit drafting · **judge:** one-time unit admission |
| relevance | question + answer | `[0,1]` (off-ask capped) + band | cosine average (A); off-ask cap; composition | grounding-relevance (B) / embeddings (A), thresholded | **gen:** RAGAS reverse-questions (A only) · **judge:** thin ask-fit residual |
| task_success | question + answer (+ artifacts/state) | `[0,1]` = Σ achieved·w / Σ w + band | **most outcomes:** presence, execution/test, state-match, constraint checks; all aggregation | coverage outcomes (NLI); grounded/responsive imports | **gen:** objective + outcome decomposition (pinned templates) · **judge:** adequacy outcomes only |

Read the table left-to-right as the audit ledger: the **T1** and **T2** columns replay exactly (T1 bit-for-bit, T2 from stamped fixed-model outputs); **T3-gen** is frozen and τ-validated per §0.5, so it's stable across a certification run even though a model produced it; and the **judge** is the sole non-replayable element, deliberately cornered into the narrowest residues (accuracy's unsourced claims, completeness's one-time admission, relevance's ask-fit edge, task_success's adequacy outcomes). Gates and the bulk of every score live in the T1/T2 columns — that distribution is the design maximizing determinism and auditability.

## Sources

Factuality / claim decomposition
- [VeriScore](https://aclanthology.org/2024.findings-emnlp.552/) — Song et al., EMNLP 2024 (verifiable-only extraction)
- [DnDScore](https://aclanthology.org/2025.emnlp-main.1205.pdf) — EMNLP 2025 (decontextualized verification)
- [Importance-sensitive factuality — "All Claims Are Equal…"](https://arxiv.org/pdf/2510.07083) — 2025
- [HHEM factual-consistency classifier / RAGAS overview](https://www.vectara.com/blog/evaluating-rag) — Vectara
- FactScore (Min et al. 2023), SAFE (Wei et al. 2024), Molecular Facts (Gunjal & Durrett 2024), Claimify (Metropolitansky & Larson 2025), decomposition-sensitivity (Wanner et al. 2024), MiniCheck (Tang et al. 2024) — *no stable public link captured; cite by name*

Nugget recall / rubric decomposition
- [The Great Nugget Recall / AutoNuggetizer](https://dl.acm.org/doi/10.1145/3726302.3730090) — Pradeep et al., SIGIR 2025 (τ = 0.87)
- [TREC 2025 RAG overview](https://arxiv.org/pdf/2603.09891) — strict vital recall, sub-narratives
- [Qworld — question-specific binary-criteria trees](https://www.alphaxiv.org/overview/2603.23522) — Gao et al., 2026
- [Rubrics survey (HD-Eval, ExpertLongBench, LLM-RUBRIC)](https://arxiv.org/pdf/2606.08625) — 2026
- [Rubric Is All You Need — question-specific rubrics](https://dl.acm.org/doi/10.1145/3702652.3744220) — Pathak et al., 2025
- [LLM-generated rubrics (RubricRAG, LEGIT over-acceptance)](https://www.emergentmind.com/topics/llm-generated-rubrics)
- [Decomposed criteria-based eval (CheckEval, RAGCHECKER discussion)](https://aclanthology.org/2025.emnlp-industry.136.pdf)
- Voorhees nuggets (2003), ARGUE (Mayfield et al. 2025) — *cite by name*

Relevance / grounding
- [RAGAS answer-relevancy](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/answer_relevance/) — reverse-question + cosine
- [AWS Bedrock Guardrails (contextual grounding, relevance)](https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-components.html)
- [fairseq RoBERTa-MNLI via torch.hub](https://pytorch.org/hub/pytorch_fairseq_roberta/) — non-HF NLI
- "Knowing When You Don't Know" (Thakur et al., EMNLP 2024) — *cite by name*

task_success / agent goal-completion
- [Hitchhiker's Guide to Agentic AI](https://arxiv.org/pdf/2606.24937) (2026) — deterministic-oracle TSR, graded success, test-execution
- [SafeAgentBench](https://arxiv.org/pdf/2412.13178) (2024) — execution evaluator + semantic-evaluator residual
- [Unified Framework for LLM Agentic Capabilities](https://arxiv.org/pdf/2605.27898) (2026) — hash-based terminal-state matching (τ-bench)
- [Generalizability of LLM Agents survey](https://arxiv.org/pdf/2509.16330) (2025) — rule-based/constraint success validation
- [KDD 2025 Agent-Eval tutorial](https://sap-samples.github.io/llm-agents-eval-tutorial/2025_KDD_Evaluation_and_Benchmarking_of_LLM_Agents.pdf) — subgoal decomposition + sum; SWE-bench
- Konstantinou et al., ICST 2025 — humans validate ground-truth assertions; never agent-authored — *cite by name*



Migrating to new Machine:
1. Get the code over

Copy the repo (or clone) onto the new machine.

2. Install

Run ./install.sh — installs pinned requirements.txt, downloads the spaCy model (en_core_web_lg) and coreferee English model.
Optional: if you want local NLI, let it install fairseq; if it fails, skip — you'll use Bedrock for NLI instead.

3. AWS account prerequisites (one-time, console/CLI)

Confirm Bedrock model access is enabled for: the Claude model (judge) and Titan Text Embeddings V2. Opt in via the Bedrock console if not.
Create a Guardrail with the contextual-grounding policy enabled (this is what powers the grounding + relevance scores). Note its guardrail ID and version.

4. Credentials

Copy .env.example → .env, fill in your AWS profile/keys (or rely on your machine's existing AWS SSO/profile — set aws.profile accordingly).

5. Configure — one file
Edit config.yaml:

providers.mode: live (from mock)
aws.region and aws.profile
models.judge_id (your Bedrock Claude model ID)
models.embed_id (amazon.titan-embed-text-v2:0)
models.guardrail_id + guardrail_version (from step 3)
models.nli: bedrock (or fairseq if you installed it)

6. Verify before using

Run python smoke_test.py — it checks each provider by name (judge, embeddings, guardrail, spaCy/coreferee, NLI). Fix anything it flags; don't run evaluations until all pass.
Run the test suite once in live mode if you want belt-and-braces.

7. Run

Execute the fixture evaluation end-to-end once and eyeball the report; then it's ready for real inputs.