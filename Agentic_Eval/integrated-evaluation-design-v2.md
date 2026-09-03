## Integrated evaluation design (v2) — complete coverage & FP/FN accounting

**Why v2.** v1 had the right skeleton but four audit-sensitive holes: no **explainability** dimension, **harm** folded into fairness, no **evaluator-reliability** measure (the meta-level false-positive/negative), and **omission** left as a qualitative move rather than a banded metric. This version closes all four, works in every strategy from the build, adds **contestability** and an explicit **out-of-scope boundary**, and ends with a **policy coverage matrix** (§10) so completeness is demonstrated, not asserted.

---

### 1. Design principles (the strategies, named)

1. **Decompose-and-verify.** Grade an answer as many atomic, born-tagged yes/no checks, not one holistic score.
2. **Engine + governance wrapper.** Layer A measures; Layer C turns measurements into risk, evidence, and a decision; Layer B (optional) learns.
3. **Label-free by construction; label only the irreducible.** Most checks are decidable from the source, an exact rule, or a constructed case; humans label only what genuinely needs it.
4. **Two-track for RAG.** Score retrieval and generation separately and attribute the failure.
5. **Gate on safety; it can't be averaged away.** A critical failure vetoes the run regardless of quality elsewhere.
6. **Fail-closed asymmetry.** Gates are tuned to minimise *missed* failures (evaluator false-negatives) even at the cost of extra false alarms.
7. **Measure the measurer.** The harness's own false-positive/negative rate is a first-class, banded metric.
8. **Evidence is the deliverable.** Every number is traceable and replayable.

### 2. The complete dimension set

Bold rows are new or split-out in v2. "FP/FN" names which error direction the dimension primarily catches.

| Dimension | DIM | Metric | Label source | Tier / gate | Catches |
|---|---|---|---|---|---|
| performance / answer_correctness | 01/02 | accuracy, F1, error rate | synthetic + human sample | MAJOR | FP + FN |
| factual_consistency (faithfulness) | 54 | unsupported-claim rate | free (source) | MAJOR | FP (commission) |
| **completeness / omission** | 01 | **source-recall + seeded-catch rate** | free + human sample | MAJOR | **FN (omission)** |
| source_quality | — | 4-property score | free + judge | MAJOR (gate high-stakes) | FP |
| point_in_time / look_ahead | 05 | leakage rate; alpha-decay | free (as-of harness) | CRITICAL · gate | FP |
| entity_resolution | — | entity-error rate | free | MAJOR | FP |
| abstention_calibration | — | correct-abstention; calibration error | free | MAJOR | FN (fabricates vs declines) |
| **explainability** | 32/33 | **reasoning-fidelity + human usefulness** | free + human sample | MAJOR | FP (bad rationale) |
| **harm** | 07 | **harmful-output rate / harm score** | free (rule + judge) | CRITICAL · gate | FP |
| injection_resistance (incl. indirect) | 53 | attack success rate | free (canary/payload) | CRITICAL · gate | FN (missed attack) |
| data_leakage / privacy | 38/16 | leakage / membership-inference rate | free (constructed) | CRITICAL · gate | FP |
| source_fabrication | 54 | fabricated-citation rate | free (deterministic) | CRITICAL · gate | FP |
| regulatory_compliance | — | breach rate | free (rule) | CRITICAL · gate | FP |
| fairness | 42/43 | ΔFPR / ΔFNR / disparity ratio | free (counterfactual) + human | MAJOR* | FP **and** FN |
| robustness / stability | 05 | paraphrase variance | free | MAJOR | FP + FN |
| drift (monitoring) | 05 | KL / error-rate change | free (time-series) | MAJOR | FP + FN |
| monitoring_completeness | 27 | % risk covered by KRIs | free | MINOR | — |
| traceability | 26 | % evidence complete | free | MINOR | — |
| unbounded_consumption | — | cost / latency per task | free | MINOR (agentic) | — |
| **evaluator_reliability (meta)** | — | **evaluator FP & FN vs human sample** | human sample | MAJOR (gate if poor) | **measures the harness itself** |

\*Re-tier `fairness`, `source_quality`, and `harm` upward in regulated deployments — they are conduct issues, not merely quality.

### 3. Rate calculations, including the new ones

Each metric reduces a dimension's binary verdicts to one banded number (unchanged for the v1 metrics — attack success rate, unsupported-claim rate, ΔFPR, drift, etc.). The additions:

- **Omission rate (completeness, now measured).** Two label-free components: **source-recall** = of the material facts present in the retrieved set, the fraction reflected in the answer; **seeded-catch rate** = of deliberately planted material documents, the fraction the answer surfaces. Report both with a **confidence interval and a minimum sample size**, so no omission rate is ever declared on noise. The irreducible novel-omission residue is a small human-labelled recall check.
- **Explainability (reasoning-fidelity + usefulness).** Decompose the answer's stated rationale into steps and check each is **entailed by the cited evidence** (reasoning-faithfulness, label-free), score **fidelity vs ground truth** where a reference exists, and add a **sampled human usefulness rating (1–10)**. Kept strictly distinct from traceability (the audit record) and transparency (disclosure) — the pitfall your policy names.
- **Harm (split out).** A dedicated **harmful-output rate / harm score** with its own band and L×I, no longer hidden inside fairness.
- **Evaluator reliability (the meta-metric).** See §4 — this is the one that actually closes the FP/FN loop.

### 4. Accounting for false positives and negatives — at two levels

This is the heart of "does it get the job done," and it has to be done at both levels or it isn't done.

**Level 1 — the agent under test.**
- **Commission (agent false positive):** asserting something wrong, unsupported, fabricated, or misattributed. Caught by faithfulness, fabrication, entity-resolution, and source-quality — the design's strong suit.
- **Omission (agent false negative):** failing to surface something material. Now a **measured, banded metric** (§3) rather than a hope: source-recall + seeded-catch, with confidence intervals.
- **Where ground truth exists (correctness, fairness):** report the **full confusion matrix** (TP/FP/TN/FN) per cohort, not a single rate, so both error directions are visible.

**Level 2 — the evaluator itself (new in v2, and the biggest hole in v1).** Every Red band and every gate is produced by a scorer that can be wrong:
- **Evaluator false positive:** fails a good answer → spurious Red/gate → unnecessary Remediate (cost: friction, over-blocking).
- **Evaluator false negative:** passes a bad answer → false Green/Approve → **the dangerous direction: a real failure ships.**
- **Measurement:** against the **human-validated sample**, compute the evaluator's **precision, recall, FPR and FNR per scorer/dimension**, band it as `evaluator_reliability`, and stamp it in the evidence pack. You cannot defend an L×I to a validator without stating the harness's own error rate.
- **Deliberate asymmetry (state it explicitly):** **gate scorers are tuned for near-zero evaluator false-negatives** (never miss an attack, leak, or fabrication) accepting more false alarms — fail-closed; **quality scorers report both directions**, because a false Green is worse than a false Red.
- **Controls that push evaluator error down (already in the design, now tied to the metric):** deterministic scorers on the gates (near-zero error), the **cross-family 2LoD challenge** (catches self-preference false-negatives), 2-run averaging (kills variance flips), fail-closed on steer/unparseable inputs, and the leniency/verbosity/position hardening.
- **Where the recursion stops:** the evaluator is measured against humans, and the human labelling carries its own **inter-rater agreement** number. That anchor — reported, not hidden — is the honest floor; nothing claims to be more reliable than the humans it was checked against.

### 5. The label-free frontier (and the irreducible human cost)

- **Free / constructed (no labels, can gate):** retrieval, faithfulness, point-in-time integrity, entity resolution, injection, leakage, fabrication, abstention, compliance rules, source-quality sub-checks, harm rules, reasoning-fidelity, counterfactual fairness, cost.
- **Synthetic (drafted by a cross-family model, source-verified):** answer correctness and completeness-vs-source.
- **Human (the only irreducible spend):** sample-validating the synthetic set, the novel-omission recall sample, the source-quality disinterest sample, the explainability usefulness rating — and, crucially, the sample that **measures evaluator reliability** (§4).

### 6. Cross-cutting strategies, integrated

- **Source quality** = four checkable properties: good source, supports *this* claim, independently corroborated, disinterested — with "conflicting / insufficient sourcing" as a detectable abstention outcome, not a score.
- **Completeness/omission** = the four moves (requirement-diff, source-recall, known-item seeding, overconfidence proxy) now feeding the §3 omission metric.
- **Point-in-time** = retrieval timestamp integrity (deterministic, zero-tolerance) plus a behavioural post-cutoff / alpha-decay test for parametric look-ahead.
- **Synthetic golden** = generate-then-verify: cross-family model, oracle context, accept only if source-verified, human-sample-validated, versioned to the corpus.
- **Security** = injection (direct and indirect via a poisoned retrieved doc), leakage across entitlement boundaries, deterministic fabrication gate; the judge treats the graded answer as untrusted data and fails closed.
- **Evaluator hardening** = provenance stamping (who judged), cross-family challenge, deterministic gates, leniency/verbosity/position guards, φ-dedup — all now *measured* by `evaluator_reliability`.

### 7. Governance pipeline (with the additions)

`Risk → Dimension → Metric → Threshold(G/A/R) → Score(L×I) → Evidence → Decision`, with monitoring across it. Gates force Remediate/Escalate; the aggregate is the OSFI E-23 model-risk rating (materiality × vulnerability). New in v2:

- **Contestability / oversight.** A disposition can be **contested and overridden** by the accountable owner (an `Accept-risk` with attestation) or **challenged by 2LoD**; every override is logged with rationale — the human-in-the-loop path your policy's oversight/contestability lines require.
- **Cross-dimension correlation.** φ-dedup handles redundancy *within* a dimension; **across** dimensions the **max-governs** aggregation prevents correlated risks (e.g. faithfulness and source-quality) from being naively summed into an inflated total — the "don't treat dimensions as independent" pitfall, handled at the aggregate level too.
- **Evidence** carries the new fields: the evaluator-reliability figures, the omission confidence intervals, the explainability ratings, and the human inter-rater agreement — versioned, timestamped, attributable, ≥7-year retention. Anchors: OSFI E-23/B-10, NIST AI RMF, ISO 42001/23894, OWASP LLM Top 10.

### 8. Explicit out-of-scope boundary

So "all metrics" is not overclaimed: **operational resilience** — availability, business continuity / disaster recovery, third-party SLA uptime, infrastructure attacks — is **not** an answer-quality concern and is **out of scope** for this harness. It belongs to operational-resilience testing (OSFI E-21, B-10 operational). This harness covers the model/answer, data/privacy, ethics/social, and compliance/governance metric families; it deliberately does not cover the resilience family, and the record says so.

### 9. Profiles

The dimension set and thresholds specialise per system: the **RavenPack** profile (open-world RAG, point-in-time first-class, source-quality heavy, E-23 third-party) and the **Nexa** profile (closed-book RAG, access-control and indirect-injection gates, synthetic golden) are their own documents; v2 is the shared framework both instantiate.

### 10. Policy coverage matrix

| Policy requirement | Covered | Where |
|---|---|---|
| Risk mapping (Atlas stripe + control objective) | yes | §7 |
| Performance (DIM-01/02) | yes | §2 |
| Drift (DIM-05) | yes | §2, monitoring §7 |
| Hallucination (DIM-54) | yes | §2 faithfulness + fabrication |
| **Harm (DIM-07)** | **yes — split out in v2** | §2, §3 |
| Prompt injection (DIM-53) | yes | §2 (direct + indirect) |
| Fairness (DIM-42/43) | yes — ΔFPR/ΔFNR + ratio | §2, FP/FN §4 |
| Privacy (DIM-16/38) | yes | §2 |
| **Explainability (DIM-32/33)** | **yes — added in v2, kept ≠ transparency** | §2, §3 |
| Monitoring (DIM-27) | yes | §7 |
| Traceability (DIM-26) | yes | §2, evidence §7 |
| Thresholds G/A/R (mandatory) | yes | §7 |
| L×I scoring | yes | §7 |
| Evidence (timestamp/version/reviewer, 7y) | yes | §7 |
| Dispositions (5) + **contestability** | yes — override path added | §7 |
| Program KPIs | yes | §7 |
| 3LoD roles | yes | §7 |
| Regulatory anchors | yes | §7 |
| No Yellow severity | yes | §7 |
| **False positives & negatives (agent + evaluator)** | **yes — both levels, banded** | **§4** |
| Pitfall: missing thresholds | yes — hard-rejected | §7 |
| Pitfall: dimensions independent | yes — φ within + max-governs across | §7 |
| Pitfall: explainability ≠ transparency | yes — kept distinct | §3 |
| Resilience / BC-DR / availability | **out of scope (stated)** | §8 |

**Verdict.** With the four additions — explainability, harm split-out, the omission metric, and above all the **evaluator-reliability (meta-FP/FN) metric** — plus the contestability path and the stated resilience boundary, the design covers every required metric family and accounts for false positives and negatives at both the agent and the evaluator level. The one honest caveat that remains by nature, not by omission: every reliability claim is anchored to a human-validated sample and is only as good as that sample's inter-rater agreement — which is why that number is reported in the evidence, not hidden.
