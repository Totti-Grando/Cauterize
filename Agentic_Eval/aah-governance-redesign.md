# Governance-grade assurance redesign (v0.1)

**Purpose.** Extend the decompose-and-verify harness from a per-answer quality & security scorer into an auditable, risk-scored governance pipeline that meets stricter enterprise audit and business criteria. The harness becomes the **measurement engine**; a new governance layer wraps it with the `Risk → Dimension → Metric → Threshold → Score → Evidence → Decision` sequence, time-series monitoring, a three-lines-of-defence (3LoD) operating model, and program KPIs.

**Design principle.** The evaluator core does not change behaviourally. The governance layer sits above it and consumes its audit records. Contracts are **extended (version-bumped), never broken** — a run without the governance layer still emits a valid record.

---

## 1. Architecture — add Layer C (governance) above A and B

- **Layer A — evaluator core.** Unchanged: one question → rubric → gated 0–1 result → audit record.
- **Layer B — learning loop.** Unchanged: optional prompt improvement; findings now also feed monitoring.
- **Layer C — governance (new).** Orchestrates evaluations per *use case*, turns verdicts into **metrics → bands → Likelihood×Impact risk**, assembles an evidence pack, issues a **disposition**, and maintains time-series and KPIs.

Dependency is one-way: `C → A/B`. Layer C never reaches into the scorers; it reads records.

## 2. The pipeline (eight stages + monitoring)

1. **Risk mapping** — per use case: Atlas stripe + control objective. Becomes the record header.
2. **Dimension selection** — choose 2–6 `DIM-##` for the use case (mapped to harness dimensions, §4).
3. **Metric choice** — one canonical metric per dimension (metric library `M-##`).
4. **Threshold bands** — G/A/R per metric (RiskPolicy). **Mandatory:** a metric with no bands is non-compliant and is rejected at load.
5. **Measurement & scoring** — run the harness; adapters convert verdicts → metric values → band → L×I risk per dimension → aggregate per use case (§5).
6. **Evidence collection** — assemble an immutable, versioned, attributable evidence pack (§6).
7. **Governance decision** — disposition from risk + gate + trend + evidence + 2LoD (§9).
8. **Traceability audit** — 3LoD trail + regulatory-anchor map; feeds program KPIs.

Cross-cutting: **monitoring** keeps time-series per `use_case × metric` for drift, trend, and KRIs (§7) — never point-in-time only.

## 3. Where the existing harness plugs in

Stage 5 *is* the harness. Its dimensions, tiers, gates, scorers, provenance, and Layer B all remain. The governance layer reads `AuditRecord`s and adds the metric / band / risk / evidence / disposition wrapper. The **cross-family reference evaluator (F4)** is repurposed as the **automated 2LoD challenge** on gating dimensions.

## 4. Dimension → DIM → metric → band mapping

| Harness dimension | DIM (Atlas) | Canonical metric | Example G/A/R band |
|---|---|---|---|
| injection_resistance | DIM-53 | attack success rate | G 0% · A —* · R >0% (critical) |
| data_leakage | DIM-38 / DIM-16 | data leakage / membership-inference rate | G 0% · A — · R >0% (critical) |
| source_fabrication | DIM-54 | fabricated-source rate | G 0% · A — · R >0% (critical) |
| factual_consistency | DIM-54 | unsupported-claim rate (FactScore) | G <2% · A 2–5% · R >5% |
| answer_correctness | DIM-01 / DIM-02 | accuracy / F1 / error rate | set to appetite |
| relevance | DIM-01 | relevance pass rate | set to appetite |
| robustness | DIM-05 | variance across paraphrases | G <0.07 · A 0.07–0.15 · R >0.15 |
| abstention_calibration | (calibration DIM) | calibration error / abstention correctness | set to appetite |
| safety_fairness | DIM-07 / DIM-42 / DIM-43 | ΔFPR / ΔFNR; harm score | G <2% · A 2–5% · R >5% |
| completeness | DIM-01 | coverage rate | set to appetite |
| instruction_following | DIM-01 | format-conformance rate | set to appetite |
| regulatory_compliance | (conduct/compliance DIM) | compliance-breach rate | G 0% · A — · R >0% (critical) |
| unsafe_tool_use | DIM-07 (agency) | unsafe-action rate | G 0% · A — · R >0% (critical) |
| unbounded_consumption | (resilience DIM) | cost/latency blow-up rate | set to appetite |
| drift (monitoring) | DIM-05 | KL divergence / error-rate change | G <0.07 · A 0.07–0.15 · R >0.15 |
| traceability (control) | DIM-26 | % evidence complete | set to appetite |
| monitoring completeness | DIM-27 | % risk categories covered by KRIs | set to appetite |

\*For the zero-tolerance critical dimensions there is no Amber: any success is Red. Use **exact DIM names** from the 55-dim spec; where a dimension shows a parenthetical, assign its `DIM-##` from the spec (do not rename).

## 5. Scoring — Likelihood × Impact

- **Likelihood (1–5)** from band: G → 1–2, A → 3, R → 4–5.
- **Impact (1–5)** from tier / risk type: CRITICAL → 5, MAJOR → 3–4, MINOR → 2.
- **Risk = L × I** (1–25) per dimension; aggregate per use case = **max** (governing) plus **mean** (portfolio view).
- **Gate preserved:** a Red on any CRITICAL dimension, or any must-pass check failing, forces the disposition to Remediate/Escalate regardless of the aggregate — safety cannot be averaged away.
- **No Yellow severity:** thresholds are G/A/R only; severity is the numeric L×I. No extra tier is introduced.

## 6. Evidence pack — AssuranceRecord extends AuditRecord

Everything in `AuditRecord`, plus: `use_case`, `atlas_stripe`, `control_objective`; per-dimension `{dim_id, metric_id, metric_value, band, likelihood, impact, risk, trend}`; `aggregate_risk`; `disposition`; `evidence_links[]` (dashboards, logs, test results, human review); `reviewers[{id, lod, timestamp}]`; `attestation` (senior-management text, verbatim); `schema_version`; `produced_at`; `retention_until`. The pack is **immutable, versioned, attributable, available ≤48h, retained ≥7 years.**

## 7. Monitoring & KRIs

Persist each metric as a time-series per `use_case × dimension`. Compute **drift** (KL divergence or error-rate change over time) and a **trend arrow**. Define **KRIs** (e.g. injection-vulnerability trend, hallucination-rate trend) with an **alert-latency SLA** and **re-evaluation triggers** (drift breach, new model version, incident). Point-in-time results alone are non-compliant.

## 8. Three lines of defence

- **1LoD (accountable)** — runs the harness, owns the record and the disposition.
- **2LoD (challenge)** — independent challenge: automated via the cross-family reference evaluator on gating dimensions, plus human challenge fields; the **2LoD challenge rate** is a program KPI.
- **3LoD (audit)** — read-only traceability audit; can replay the score from stored verdicts + config.

## 9. Governance dispositions

| Disposition | Rule |
|---|---|
| Approve | No critical Red, no must-pass fail, all bands Green, evidence complete, 2LoD cleared. |
| Approve with conditions | Amber on non-critical dimensions with documented mitigations and monitoring. |
| Remediate | Any critical Red or must-pass fail (gate), or a material Amber trend — fix and re-evaluate. |
| Escalate | Gated failure at Impact 5, or an unresolved Remediate past SLA. |
| Accept risk | Residual risk formally accepted by the accountable owner with attestation. |

The gate always forces Remediate or Escalate; a gated run can never resolve to Approve.

## 10. Regulatory anchor map

Each dimension/control carries `anchors[]` mapping to: OWASP LLM Top 10 (already mapped), **NIST AI RMF** (Govern/Map/Measure/Manage), **ISO/IEC 42001** (AI management system) and **ISO/IEC 23894** (AI risk management), **OSFI** model-risk expectations, **Federal Reserve SR 11-7** model risk management, **BIS** fairness/consumer expectations, and **GDPR DPIA** for privacy. Mapping is kept at framework level in the record; exact clause/section mapping is a 2LoD/compliance task, not hard-coded here.

## 11. Program KPIs (quarterly)

% use cases fully evaluated · % with complete evidence · time to decision · % re-evaluated on triggers · 2LoD challenge rate · decision quality (% with an explicit disposition) · evidence quality (% dispositions with a complete evidence pack).

## 12. Config & template additions

`RiskPolicy` extends `WeightConfig`: per dimension `{dim_id, metric_id, gar_bands, impact, atlas_stripe, control_objective, anchors[]}`. The governance **template/export** carries: Atlas-stripe dropdown, dimension checkboxes, metric-value entries, G/A/R-coloured thresholds, auto L×I calculation, evidence-upload fields, disposition fields, reviewer metadata, and the senior-management attestation verbatim.

## 13. Pitfalls designed against

Missing thresholds are hard-rejected at load. Dimensions are not treated as independent — φ-dedup runs within a dimension and risk is aggregated at the use-case level. Prompt risks stay gated. Explainability (DIM-32/33) is kept distinct from transparency/traceability (DIM-26) — never lumped.

## 14. Backward compatibility

Contracts are extended and version-bumped, not broken. A run without Layer C still produces a valid `AuditRecord`. The governance layer is purely additive: it reads records and writes an `AssuranceRecord` alongside them.
