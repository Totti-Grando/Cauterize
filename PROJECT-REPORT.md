# Combined_proj — Full System Report

A single, self-contained explanation of how this project works: the architecture, the two
applications, the API that joins them, and — in detail — **how the evaluation works and is
measured**. Written to be handed to a reviewer (human or a Claude chat model).

Deep-dives referenced here live in `Agentic_Eval/docs/`:
- `evaluation-manual.md` — the full rubric (dimensions/tiers/gates) + **every prompt** + the scoring
  math, written so you can run an evaluation by hand.
- `sample-run-walkthrough.md` — one run traced end-to-end with **sample outputs at every step**
  (normal, gated-fail, adversarial, and a Layer B iteration).
- `evaluation-flow-and-audit.md` — every LLM call, exact call counts, the audit trail; **§9 is the
  authoritative description of the F1–F10 hardening**.
- `correctness-review-findings.md` — an independent multi-agent review + two-pass remediation status.
- `agent-assurance-harness-spec-v3.md` — the original design spec.

---

## 1. What this is

Combined_proj is an **AI answer–evaluation studio**. It asks a "system under test" (a chatbot /
research provider) questions, then uses an evaluator LLM to grade each answer against an
automatically generated, classified rubric — producing an auditable, reproducible quality &
security score.

Two subprojects:

| Project | Stack | Role |
|---|---|---|
| **`Agentic_Eval`** | Python 3.13 (`aah` package) | The evaluation **engine** + a FastAPI server. |
| **`Possible_UI/frontend`** | React + Vite | The **UI** — a chat-style studio with setup, live runs, results, history, settings. |

```
Browser (React, :5173)
   │  /api/*  (Vite dev proxy)
   ▼
FastAPI server  aah/api/server.py  (:8000)
   │
   ├── config_store.py   settings + secrets (gitignored config.json, masked reads)
   ├── engine.py         builds live runs (Bedrock evaluator + providers) OR fixture fallback; SSE streaming
   ├── adapter.py        AuditRecord → UI shapes
   ├── scenario.py       offline deterministic demo cases
   ├── run_store.py      saved-run history (runs.jsonl)
   └── the aah engine    Layer A (one evaluation) + Layer B (learning loop)
```

---

## 2. Repository layout

```
Agentic_Eval/
  aah/
    cli.py                 CLI entry (python -m aah.cli): demo / --live / --adversarial / --loop / --learn
    llm.py                 evaluator backends: groq | anthropic | bedrock (make_evaluator)
    contracts/             FROZEN data contracts (models.py, enums.py) — the audit schema,
                           incl. Provenance + JudgePolicy + AgentInfo (F1/F4)
    config/                tier policy table (+ OWASP LLM Top-10 map) + WeightConfig loader
    families.py            model-family detection for self-enhancement-bias flag (F1/F4)
    layer_a/
      pipeline.py          run_once(): one question → AuditRecord (provenance, gating min-runs, phi-dedup)
      question_gen.py      ClaudeQuestionGenerator (1 call/question)
      rubric_gen.py        StagedRubricGenerator (2-step decomposition: 1 + R calls)
      rubric_norm.py       normalize checks to a real scorer + guard security gates
      router.py            EvalMethod → scorer
      scorers/             deterministic | injection | fabrication (F3) | nli(+http/local, F9) | llm_judge | source_fetch
      aggregator.py        the §7 weighting + gating math (deterministic; per-dim thresholds)
      audit.py             AuditLog (append-only JSONL)
      providers/           system-under-test adapters: fixture | groq | gemini | http | (anthropic)
      seeds.py, attack_seeds.py
    layer_b/
      orchestrator.py      optimize(): the iterate → learn → patch loop
      notetaker.py         failures → classified Lessons (1 call/iter if failures)
      updater.py           Lessons → edited prompt string (1 call/iter if promptable)
      rubric_critic.py     audits generated rubrics (used by --learn)
      lessons.py, signals.py, results.py
    api/                   the FastAPI layer (server, engine, adapter, scenario, config_store, run_store, static_data)
    docs/                  the deep-dive docs (manual, sample-run, flow-and-audit, findings, spec)
    tests/                 171 offline tests (pytest)
  run_server.py            click-to-run launcher for the API
Possible_UI/frontend/
  src/
    api/                   client.js (fetch + SSE) + index.js (endpoint functions, USE_MOCK toggle)
    pages/                 01_Terms … 12_Settings (setup wizard + chat modes + results/history)
    components/            ChatShell, ChatTurn, RunInfoPanel, EvaluationCard, Card, ui.jsx, …
    lib/                   useEvalStream (SSE→transcript), saveRun, tone
```

---

## 3. How to run it

Two terminals (this machine: `python`/`node` aren't on PATH — use the venv python and prepend the Node dir):

```powershell
# Terminal 1 — backend (FastAPI on :8000)
cd C:\Users\piler\PycharmProjects\Combined_proj\Agentic_Eval
.\.venv\Scripts\python.exe run_server.py

# Terminal 2 — frontend (Vite on :5173)
$env:PATH = "C:\Program Files\nodejs;$env:PATH"
cd C:\Users\piler\PycharmProjects\Combined_proj\Possible_UI\frontend
npm run dev
```

Open http://localhost:5173. With no credentials entered, everything runs on **offline
fixtures** (deterministic, no keys, no cost). Enter AWS + provider credentials in **Settings** to
switch to live model calls.

Engine directly (no UI): `python -m aah.cli` (offline demo) or `python -m aah.cli --live --json`.

---

## 4. How the evaluation works (the core)

> Full call-by-call detail with exact counts is in `Agentic_Eval/docs/evaluation-flow-and-audit.md`.
> Summary here.

**One evaluation = one question → a rubric of atomic checks → 0/1 verdicts → a gated score.**

### Layer A — one evaluation (`layer_a/pipeline.py:run_once`)

1. **Generate the question** from a seed via the evaluator LLM — **1 call**.
2. **Fork (concurrent):**
   - **Build the rubric** via the two-step decomposition (`StagedRubricGenerator`): 1 call to
     enumerate *Requirements* (≤ 8), then 1 call *per requirement* to write atomic true/false
     `BinaryQuestion`s → **1 + R calls**. Each check is *born tagged* with
     `{dimension, subtype, eval_method, must_pass, check_directive}` so a failing verdict is
     already classified.
   - **Query the system-under-test** N times (`runs`, default 1).
3. **Score every check, per run:** the router sends each check to its scorer —
   `deterministic`/`injection` are **0-call** (exact rules), `llm_judge`/`nli` are **1 call** each.
4. **Combine runs** (if N ≥ 2): 2-run averaging resolves borderline flips conservatively to 0.
5. **Aggregate** deterministically (below) and emit an immutable **`AuditRecord`**.

**Per-evaluation LLM-call formula:** `1 (question) + (1 + R) (rubric) + N·(1 + Q_llm)`
where `Q_llm` = checks graded by an LLM (deterministic/injection checks are free).
A UI "5-question run" = 5 independent Layer A evaluations.

### How the score is measured (`layer_a/aggregator.py`, §7)

Deterministic function of `(verdicts, WeightConfig)`:

1. **Tier** each dimension (the one human input, `config/policy.py`): `CRITICAL` (gating),
   `MAJOR` (weight 2), `MINOR` (weight 1).
2. **Per-dimension score** `S_d` = uniform mean of that dimension's 0/1 checks.
3. **Cross-dimension weight** `w_d = tierweight(d) / Σ tierweight` over the scored (MAJOR+MINOR)
   dimensions only (CRITICAL dims carry weight 0).
4. **Gating dominates:** if any CRITICAL dimension `S_d < threshold` (default 1.0) **or** any
   `must_pass` check scored 0 → **overall = 0.0, FAIL**, attributed to `gated_by`.
   Otherwise **overall = Σ w_d · S_d** (clamped to [0,1]).

So safety-critical failures hard-fail the run and **cannot be averaged away** by good quality
scores — the central defensibility property.

### Layer B — the learning loop (`layer_b/orchestrator.py:optimize`)

Wraps Layer A. Each iteration: run Layer A → collect **failures** → (`--learn`) a rubric
**critic** audits the rubric → **NoteTaker** turns failure explanations into classified
**Lessons** (promptable vs structural) → **Updater** edits the prompt string (`P_Q` or rubric
guidance) via locate-substring-then-replace with a length budget → repeat until a convergence
condition (`no-new-signal` / `no-promptable-lessons` / `prompt-stable` / `max-iterations`).
Structural lessons (genuine provider limits) are **logged, not injected** — the loop can't paper
over a real capability gap.

### Defensibility hardening (F1–F10)

Beyond the base flow, the engine adds: **provenance** on every record (who judged / who was judged,
F1); **prompt-injection hardening** of the judge/NLI (fence the answer as untrusted data, fail
closed, F2); a **deterministic source-fabrication gate** — cited URLs/quotes must be in the provided
context (F3); **self-enhancement-bias controls** (same-family flag + optional cross-family reference
judge / panel for gates, F4); **per-dimension gate thresholds + ≥2 runs for gating dims** (F5);
**leniency/yes-bias monitoring** (F6); **verbosity/position guards** (F7); **φ-dedup of redundant
checks before averaging** (F8); a **constrained NLI slot** (Claude/HTTP/optional-local, F9); and
**OWASP LLM Top-10 mapping** on the CRITICAL gates (F10). Full detail in `evaluation-manual.md` and
`evaluation-flow-and-audit.md` §9.

---

## 5. The audit trail (why a result is trustworthy)

Every evaluation emits an immutable **`AuditRecord`** (`schema_version: "v1"`, `contracts/models.py`),
persisted one per line as JSONL (`layer_a/audit.py`). It carries: mode, task, question, response, the
full rubric (every classified check), every verdict (0/1 + **mandatory explanation** + evidence +
`attack_success`), the per-dimension scores, the gated `overall`/`failed`/`gated_by`, the full
**`WeightConfig`**, the **`provenance`** (evaluator + provider `{backend, model, version, params}` and
`same_family_judge`, F1), and the per-dimension **`yes_rate_summary`** (F6).

**Reproducibility, precisely:** the *scoring function* is deterministic — the same verdicts + same
`WeightConfig` always replay to the same score (`§7.6`), and the config travels in the record. The
*verdicts themselves* are not deterministic across model versions (they come from an LLM judge),
which is exactly why the evaluator identity is stored next to them (F1). Contracts are frozen
(`extra="forbid"`), so schema drift fails loudly. Saved UI runs (`run_store.py`) also stamp
`source: live|fixture`, so fixture results can't be misattributed to a real model.

---

## 6. The three modes (UI)

All three share one chat-style shell (`components/ChatShell.jsx`) with a top-corner **"Run info"**
drawer (config, live metrics, timestamped log). Live output streams over SSE.

- **Manual** (`06_Workspace.jsx`): you type a question → provider answers → answer is evaluated → ask again.
- **Assisted** (`07_AssistedReview.jsx`): the evaluator model **drafts an editable question** (+ tips); you edit → Ask.
- **Automatic** (`08_RunMonitor.jsx`): the pipeline runs itself and streams question → answer → evaluation per item; auto-saves to history on completion.

---

## 7. Live vs offline, and credentials

`engine.is_live_ready()` gates live execution: a run is **live** only when the chosen evaluator
(Bedrock/Anthropic/Groq) *and* the selected provider have usable credentials; otherwise it
**falls back to the deterministic `scenario.py` fixtures** (and says so). Secrets are entered in
Settings, stored server-side in a gitignored `config.json`, masked on read (`{configured, last4}`),
and applied to the environment for the engine. The default evaluator model is Bedrock Claude
(`aah/llm.py`), and the harness's Claude components default to `claude-opus-4-8`.

---

## 8. Quality status (independent review + hardening)

An independent multi-agent review found and adversarially verified **19 issues**. First pass fixed
the critical + high-value set; a second pass (the **F1–F10** defensibility backlog) added provenance,
injection hardening, the deterministic fabrication gate, bias controls, per-dimension gate policy,
leniency/verbosity guards, φ-dedup, the constrained NLI slot, and the OWASP mapping. Tests: **171
passing** (each F-item has its own test). Full detail + two-pass remediation status:
`Agentic_Eval/docs/correctness-review-findings.md`.

Remaining known limitations (documented, not hidden): `normalize_rubric` still routes non-directive
`nli` checks to the judge by default (the constrained NLI slot must be wired explicitly for
response-aware grounding); the UI/API streaming path is single-pass while the `run_once` path runs
gating dims ≥2×; and a couple of low-severity items (empty-rubric error status, source-fetch abstain)
are still open. The central gate property is preserved throughout: **safety-critical failures
hard-fail and are never averaged away.**

---

## 9. Tech notes / gotchas

- Backend deps: `fastapi`, `uvicorn`, `boto3` (installed in the venv); live Bedrock evaluator also
  needs `anthropic[bedrock]`.
- `node`/`npm` live at `C:\Program Files\nodejs` (not on PATH); the venv python is at
  `Agentic_Eval/.venv/Scripts/python.exe`.
- If the API fails to start with "only one usage of each socket address", a previous `run_server.py`
  still holds port 8000 — stop it first.
- `USE_MOCK` in `src/api/client.js` defaults to live; set `VITE_USE_MOCK=true` for a UI-only run
  with no backend.
