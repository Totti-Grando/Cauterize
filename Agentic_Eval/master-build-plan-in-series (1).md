# Master build plan — governance + RavenPack + Nexa, in series

**Goal:** take the current evaluator core (Layer A + Layer B, no Layer C, no profiles) to a full state — the governance layer plus both profiles — in three sequenced stages. Each stage has its own detailed design doc; this plan gives Claude Code the **order, dependencies, reuse, and the acceptance gate between stages**.

## Why this order

```
current core (Layer A + B)
      │
      ▼
Stage 1  Layer C — governance         ← the shared foundation both profiles plug into
      │
      ▼
Stage 2  RavenPack profile            ← introduces the shared RAG measurement
      │
      ▼
Stage 3  Nexa profile                 ← reuses Layer C + the shared RAG measurement
```

Governance is built first because both profiles produce the same risk-rated, evidence-backed record; building it once stops each profile re-implementing scoring and evidence. RavenPack goes second because it introduces the shared RAG primitives (retrieval trace, two-track attribution, synthetic golden, cross-family challenge) that Nexa also needs. Nexa goes third and reuses all of it, adding only its own gates and the missing-info method.

## Global rules (apply to every stage)

- **Plan mode per stage.** Produce a plan, review it, then implement. Do not start a stage until the previous one is merged and all tests are green.
- **Contracts extended, never broken.** Version-bump the record schema; a run from any earlier stage must still validate.
- **Each stage keeps all prior tests green** and adds its own.
- **Reuse over rebuild.** The components flagged "shared" are built once (Stage 2) and reused (Stage 3), not duplicated.

---

## Stage 1 — Governance layer (Layer C)

- **Inputs:** `@aah-governance-update-order.md` — the single authoritative item list (G1–G16). `@integrated-evaluation-design-v2.md` and `@aah-governance-redesign.md` are **reference / rationale only**; every requirement is already captured as a G-item, so Claude Code builds from the order, not the framework docs.
- **Depends on:** the existing Layer A (aggregator, gate, `AuditRecord`, `WeightConfig`).
- **Deliverables:** G1–G10 — `RiskPolicy` (extends `WeightConfig`); `AssuranceRecord` (extends `AuditRecord`, version-bump); metric-adapter registry; G/A/R banding; L×I scoring; disposition engine; evidence pack (immutable, versioned, attributable, ≥7-year retention); 3LoD including the cross-family reference as the 2LoD challenge; monitoring / drift / KRIs; program KPIs. G11–G16 (the v2 completeness items, now folded into the order) — the **evaluator-reliability** meta-metric (harness FP/FN vs a human sample), the explainability dimension (kept distinct from traceability), harm split out as its own gate, omission promoted to a banded metric with a confidence interval, the contestability / override path, and the explicit out-of-scope resilience boundary.
- **Reuse:** consumes existing `AuditRecord`s; the existing aggregator and gate stay unchanged.
- **Acceptance gate:** a generic evaluation now also emits an `AssuranceRecord` with a banded L×I risk, a disposition, and an evidence pack; the gate still forces Remediate/Escalate; `evaluator_reliability` computes against a human sample; thresholds are mandatory (no bands → non-compliant); all prior tests green.
- **Checkpoint:** review before Stage 2.

## Stage 2 — RavenPack profile (introduces the shared RAG measurement)

- **Inputs:** `@ravenpack-evaluation-strategy.md`.
- **Depends on:** Stage 1.
- **Deliverables:**
  - **2a — shared RAG measurement (build once, reused by Nexa):** provider retrieval trace (citations / chunk ids); two-track retrieval-vs-generation attribution; the synthetic-golden builder (cross-family model + oracle context + source-verify + provenance + version-to-corpus-hash); cross-family reference wiring (partly already in Stage 1's 2LoD).
  - **2b — RavenPack-specific measurement:** the source-quality four-property scorer (good / supports-this-claim / independently-corroborated / disinterested); the point-in-time / look-ahead harness (retrieval timestamp integrity as a zero-tolerance gate, plus the behavioural post-cutoff / alpha-decay test for parametric look-ahead); the entity-resolution scorer; the completeness moves feeding the omission metric.
  - **2c — RavenPack RiskPolicy:** dimension → DIM → metric → G/A/R bands; tiers and gates; OSFI E-23 / B-10 anchoring (RavenPack is a third-party model, so the record doubles as the B-10 vendor file).
- **Acceptance gate:** a RavenPack run produces an `AssuranceRecord` with the RavenPack dimensions banded and L×I-scored, point-in-time leakage gating, and the E-23 mapping; the shared RAG primitives (2a) are factored so Nexa can reuse them; tests green.
- **Checkpoint:** review before Stage 3.

## Stage 3 — Nexa profile (reuses Stage 1 + Stage 2)

- **Inputs:** `@nexa-evaluation-design-v2.md` and the item list in `@nexa-update-order-standalone.md` — **but now wired into Layer C rather than deferred**, since governance exists after Stage 1.
- **Depends on:** Stages 1 and 2.
- **Deliverables:** the `nexa` provider (retrieval trace + entitlement context); the known-item test-set builder (gold written backward from a chunk — no second indexer); the retrieval-recall scorer; the source-recall / omission scorer (banded, with a confidence interval); the access-control gate routed into the existing `data_leakage` critical dimension; the indirect-injection harness routed into `injection_resistance`; the fabrication extension routed into `source_fabrication`; the abstention harness (out-of-corpus + remove); the structural oracles; and the `nexa` RiskPolicy. **Governance wiring is included now** — the standalone order's "governance deferred" note is satisfied by Stage 1.
- **Reuse:** the two-track attribution, retrieval trace, synthetic-golden builder, and cross-family challenge from Stage 2; all of Layer C from Stage 1.
- **Acceptance gate:** a Nexa run produces an `AssuranceRecord` with the Nexa dimensions and gates, missing-information detection with no competing indexer, and an L×I disposition through Layer C; tests green.

---

## Final acceptance

All three run end to end; the profile (`ravenpack` / `nexa`) is selectable; contracts are version-bumped and backward compatible; the full test suite is green. A single generic evaluation, a RavenPack evaluation, and a Nexa evaluation each produce a valid, risk-rated, evidence-backed `AssuranceRecord` through the same Layer C.

## Note on the earlier standalone Nexa order

`nexa-update-order-standalone.md` deliberately deferred governance because it assumed Layer C did not exist. In this series Layer C is Stage 1, so at Stage 3 the Nexa governance wiring is folded back in — use the standalone order for its N-item detail, but treat its "out of scope: governance" section as superseded by this plan.

## How to hand this to Claude Code

Give it one stage at a time. For Stage 1:

> Read `@aah-governance-update-order.md` — it is the authoritative item list (G1–G16). In plan mode, propose an implementation plan for Stage 1 (Layer C), calling out every change to the frozen contracts. Don't write code until I approve, and don't touch the RavenPack or Nexa work yet.

Then, only after Stage 1 is merged and green, repeat for Stage 2 with `@ravenpack-evaluation-strategy.md`, and finally Stage 3 with `@nexa-evaluation-design-v2.md`.
