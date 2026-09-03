# Claude Code work order — governance layer (Layer C)

**Goal:** implement the governance layer so the harness emits, per use case, a risk-scored, evidence-backed, disposition-carrying assurance record under a 3LoD model — **complete**, including the reliability, explainability, harm, omission, contestability, and scope items. This is an additive layer over the existing evaluator core and is the single authoritative item list for Stage 1.

## How to run this

- **Authoritative order:** this file (G1–G16). `integrated-evaluation-design-v2.md` and `aah-governance-redesign.md` are **reference / rationale only** — do not treat them as build input; every requirement is captured as an item below.
- **Plan mode.** Propose a phased plan for G1–G16 and wait for approval.
- **Contracts are extended, not broken.** Version-bump the record schema; keep every existing field. A legacy run with no governance config must still produce a valid `AuditRecord`.
- **Every item ships tests.** Keep the existing tests green.
- **Do not weaken the gate property:** a critical Red or a must-pass failure can never aggregate into an Approve.

---

## Phase 1 — data model & config

### G1. RiskPolicy config
Extend `WeightConfig` into a `RiskPolicy`: per dimension `{dim_id (DIM-##), metric_id (M-##), gar_bands {green, amber, red}, impact (1-5), atlas_stripe, control_objective, anchors[]}`.
**Validate at load:** every scored dimension MUST carry G/A/R bands (zero-tolerance critical dims may omit Amber). Missing bands → reject as non-compliant.
**Accept:** a policy without bands fails to load with a clear error; the resolved policy is stamped into every record.

### G2. AssuranceRecord (extends AuditRecord)
Version-bump the schema and add: `use_case`, `atlas_stripe`, `control_objective`; per-dimension `{dim_id, metric_id, metric_value, band, likelihood, impact, risk, trend}`; `aggregate_risk`; `disposition`; `evidence_links[]`; `reviewers[{id, lod, timestamp}]`; `attestation`; `produced_at`; `retention_until`.
**Accept:** new records validate; a legacy run still produces a valid record; schema version is bumped and stamped.

## Phase 2 — metrics, banding, scoring, disposition

### G3. Metric adapters registry
Map each dimension's verdicts → a canonical metric value: `attack_success_rate`, `unsupported_claim_rate`, `fabricated_source_rate`, `delta_fpr`/`delta_fnr` (by cohort), `leakage_rate`, `calibration_error`/`abstention_correctness`, `accuracy`/`f1`, `paraphrase_variance`. Each adapter declares its extra data needs (cohort labels for fairness, repeats for stability).
**Accept:** each active dimension yields a metric value plus which adapter and inputs produced it; one test per adapter.

### G4. Banding + Likelihood×Impact
`band = f(metric_value, gar_bands)`; Likelihood from band (G→1-2, A→3, R→4-5); Impact from policy; `risk = L×I`; aggregate per use case = max (governing) + mean (portfolio). Enforce **no Yellow** — only G/A/R plus the numeric L×I.
**Accept:** known metric values map to the expected band and risk; boundary tests at each band edge.

### G5. Disposition engine
Decide `Approve / Approve-with-conditions / Remediate / Escalate / Accept-risk` from `{max risk, any critical Red or must-pass fail (gate), trend, evidence completeness, 2LoD sign-off}`. The gate forces Remediate/Escalate.
**Accept:** the rule table is encoded; each branch is tested; a gated case never returns Approve.

## Phase 3 — monitoring, 3LoD, anchors, KPIs, evidence

### G6. Time-series, drift, trend, KRIs
Persist each metric per `use_case × dimension` over time. Compute drift (KL divergence or error-rate change) and a trend arrow. Define KRIs with an alert-latency SLA and re-evaluation triggers.
**Accept:** trend and drift are computed and stored; a threshold breach raises a KRI alert; tested.

### G7. 3LoD + 2LoD challenge + attestation
Record reviewer metadata by line of defence. Wire the cross-family reference evaluator as the automated 2LoD challenge on gating dimensions; capture human challenge and senior-management attestation verbatim.
**Accept:** a 2LoD challenge is recorded; the challenge rate is computable; attestation is stored immutably.

### G8. Regulatory anchor map
Carry `anchors[]` per dimension (NIST AI RMF function, ISO 42001/23894, OSFI, Fed SR 11-7, BIS, GDPR DPIA, OWASP LLM) in the policy and stamp them in the record.
**Accept:** anchors travel in the record; a missing anchor is a warning, not a hard fail.

### G9. Program KPI aggregator
Compute over a set of records: % use cases fully evaluated, % complete evidence, time-to-decision, % re-evaluated on triggers, 2LoD challenge rate, decision quality, evidence quality — as a quarterly rollup.
**Accept:** KPIs compute over a fixture set of records; tested.

### G10. Evidence provenance + template/export
Every record is versioned, timestamped, and attributable; available ≤48h; retained ≥7 years (`retention_until` stamped; immutable store). Export a governance template with: Atlas-stripe dropdown, dimension checkboxes, metric values, G/A/R-coloured thresholds, auto L×I, evidence-upload fields, disposition, reviewer metadata, and attestation.
**Accept:** the export round-trips; evidence is immutable and attributable; retention is set.

## Phase 4 — completeness (the v2 additions)

### G11. Evaluator-reliability meta-metric
**Why:** every Red band and every gate comes from a scorer that can itself be wrong — a false positive (fails a good answer → spurious Remediate) or, worse, a false negative (passes a bad answer → false Approve). A risk rating is not defensible without the harness's own error rate.
**Change:** against the human-validated sample, compute per-scorer/dimension **precision, recall, FPR and FNR**; band as `evaluator_reliability` and stamp it in the record. Encode the **asymmetry**: gate scorers are targeted at near-zero evaluator false-negatives (fail-closed), quality scorers report both directions. Record the human sample's **inter-rater agreement** alongside.
**Accept:** evaluator FP/FN are computed against the human sample and banded; the record carries them plus inter-rater agreement; a deliberately-degraded scorer lowers the reliability band; a gate scorer whose FN exceeds target is flagged; tested.

### G12. Explainability dimension
**Why:** required as its own DIM (32/33) and must not be lumped with transparency/traceability.
**Change:** add an `explainability` dimension. Metric = **reasoning-fidelity** (decompose the answer's stated rationale into steps; each must be entailed by the cited evidence — reuse the `nli` scorer) + fidelity vs ground truth where available + a **sampled human usefulness rating (1–10)**. Keep it distinct from traceability (the audit record) and transparency (disclosure).
**Accept:** explainability scores and bands independently of traceability; a rationale step not entailed by evidence lowers it; the usefulness sample is recorded; tested.

### G13. Harm as its own dimension
**Why:** the policy treats harm (DIM-07) as its own dimension with its own metric; it is currently folded into `safety_fairness`.
**Change:** split `harm` into a standalone **gating** dimension with a harmful-output rate / harm score, its own band and L×I.
**Accept:** harm scores and gates independently of fairness; tested.

### G14. Omission as a banded metric
**Why:** completeness / agent false-negatives were qualitative; they must be measured.
**Change:** `completeness` reports **source-recall + seeded-catch** as a banded rate **with a confidence interval and a minimum sample size** — no rate is declared on noise, and below the minimum it abstains from a band rather than guessing.
**Accept:** omission is a banded rate with a CI; below min-sample no band is asserted; tested.

### G15. Contestability / override path
**Why:** the policy's oversight/contestability expectation — a decision must be challengeable and overridable, not final-by-machine.
**Change:** allow a disposition to be **contested by the accountable owner** (an `Accept-risk` with attestation) or **challenged by 2LoD**; log every override with rationale, reviewer, and timestamp; overrides are immutable, do not erase the original disposition, and are visible to 3LoD.
**Accept:** an override is recorded with rationale and preserves the original disposition; tested.

### G16. Explicit out-of-scope boundary
**Why:** so "all metrics" is not overclaimed — operational resilience (availability, BC/DR, third-party SLA uptime, infrastructure attacks) is not an answer-quality concern and belongs to operational-resilience testing (OSFI E-21, B-10 operational).
**Change:** the record and the KPI/coverage output state the covered metric families and mark **resilience explicitly out of scope**; nothing emits a resilience coverage claim.
**Accept:** the coverage output names resilience as out of scope; a test asserts no resilience claim is emitted.

---

## Definition of done — non-negotiables

- Existing tests green; each G-item has new tests.
- Thresholds are mandatory — a config with no bands is non-compliant and rejected.
- Evidence is immutable, versioned, timestamped, attributable; ≥7-year retention; ≤48h availability.
- The gate property holds: a critical Red or must-pass failure can never be averaged into an Approve.
- `evaluator_reliability` is measured and banded; explainability, harm, and omission each score and band independently; the contestability path is logged; the resilience boundary is stated.
- Exact DIM names throughout; no Yellow severity.
- Contracts extended, not broken; schema version bumped; a legacy run still produces a valid record.
