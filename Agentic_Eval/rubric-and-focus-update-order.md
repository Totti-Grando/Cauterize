# Claude Code work order — new rubric (dimension taxonomy) & focus areas

**Goal:** replace the current dimension set with the structured 10-category taxonomy (35 dimensions), adapt the Critical/Major/Minor tiers to it, and add the **focus vs coverage** weighting model — focus is selectable and steers generation and weighting, while coverage always scores every dimension and every gate stays live.

## How to run this

- **Read first:** `@evaluation-taxonomy-focus-and-personas.md` — §1 is the full dimension → tier → gating-subtype table (authoritative), §2 is the focus/coverage weighting model.
- **Plan mode.** Propose a phased plan for R1–R7 and wait for approval.
- **Build on what exists:** `config/policy.py` + `WeightConfig`, `contracts/enums.py`, `aggregator.py` (per-dim mean + weighted overall + gate), `router.py` (`eval_method → scorer`), `StagedRubricGenerator`.
- **Contracts extended, not broken.** Version-bump `WeightConfig` and `AuditRecord`; keep existing fields; map existing dimensions to their taxonomy names rather than deleting them.
- Every item ships tests; keep existing tests green.

---

## Phase 1 — the dimension taxonomy

### R1. Register the 35 dimensions
Add all dimensions from `@…§1`, grouped into the 10 categories. Each carries `{category, tier (CRITICAL/MAJOR/MINOR), gating_subtype?}`. New dimensions beyond today's set are mainly **Reasoning** (`logical_consistency`, `assumption_quality`, `uncertainty_handling`) and **Communication** (`clarity`, `structure`, `conciseness`, `actionability`), plus the finer RAG / robustness / privacy splits. Existing dimensions are **mapped to their taxonomy names, not renamed away**.
**Accept:** all 35 load with a category and tier; every current dimension resolves to a taxonomy entry; tested.

### R2. Scorer routing per dimension
Map each dimension to an `eval_method`. Reuse the existing scorers wherever possible (`deterministic`, `injection_detector`, `source_check`, `nli`, `llm_judge`, plus the RAG retrieval scorers); Reasoning and Communication dimensions route to `llm_judge` with dimension-specific prompts.
**Accept:** every dimension resolves to a scorer through `router.py`; an unresolved dimension raises at load; tested.

### R3. Gating subtypes
Implement subtype-level gates so a MAJOR dimension can still veto on a specific failure: `hallucination` → fabricated-source / invented-policy (reuse `source_check`); `constraint_compliance` → violated safety/legal restriction; `format_compliance` → hard JSON as `must_pass`; `security_compliance` → actively insecure advice. A triggered gating subtype fails the run through the **existing** gate path; a non-subtype miss only lowers the dimension score.
**Accept:** a MAJOR dimension with a triggered gating subtype fails the run via the current gate; the same dimension failing non-critically just scores lower; tested.

## Phase 2 — focus & coverage weighting

### R4. Coverage invariant
Every evaluation instantiates and scores **all** active dimensions; a dimension with no data **abstains** (contributes no band/score) rather than being skipped; **all gates are always active**. Focus can never remove a dimension or a gate.
**Accept:** with any focus set, all dimensions appear in the record and all gates evaluate; a test asserts focus cannot disable a gate.

### R5. Focus profile + effective weight
Add a selectable **focus profile** (a list of categories or sub-dimensions) to the config, plus `focus_boost` (default 2.0):
```
effective_weight(d) = tier_weight(d) × (focus_boost if d ∈ focus else 1.0)
overall = Σ effective_weight(d)·score(d) / Σ effective_weight(d)   over scored dims
gate:   unchanged — CRITICAL tier_weight is 0, gates fire independently of focus
```
**Accept:** focus raises the scored weight of focus dimensions and shifts `overall` accordingly; tiers and gates are mechanically unchanged; no focus = base weights; boundary tests.

### R6. Focus steers generation
Pass the focus profile to the question generator and `StagedRubricGenerator` as a directive, so it produces **more and deeper checks in the focus areas** (and, in probe mode, focus-appropriate probes) — while still generating checks across **all** dimensions (coverage).
**Accept:** a focus run yields extra focus-area checks but a full-coverage rubric; tested.

## Phase 3 — record & config

### R7. Record focus and weights
Stamp the focus profile and the effective weights on the `AuditRecord` (version bump). A legacy run with no focus still validates.
**Accept:** the record carries the focus profile and weights; backward compatible; tested.

---

## Definition of done — non-negotiables

- 35 dimensions registered with category, tier, and gating subtype; existing dimensions mapped, not lost.
- **Coverage invariant:** all dimensions scored (or abstained) and all gates live regardless of focus.
- Focus does two things only — steer generation and boost scored weight; it never disables a dimension or a gate.
- Tier and gate **mechanisms** are unchanged; only the weight gains the `focus_boost` factor.
- Exact dimension names; contracts extended and version-bumped; existing tests green, each R-item tested.
