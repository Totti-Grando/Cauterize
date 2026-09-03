## RavenPack (Bigdata.com) evaluation strategy (v0.1)

**What this is.** A complete strategy for evaluating RavenPack's Bigdata.com as a deployed capability inside a Canadian federally-regulated financial institution. It applies the governance framework (Risk → Dimension → Metric → Threshold → Score → Evidence → Decision), the decompose-and-verify engine, and the design work on source quality, completeness/omission, and the label-free frontier — specialised to what RavenPack actually is and to the regulation that binds its use.

---

### 1. What RavenPack is, and why it shapes the evaluation

Bigdata.com is an **agentic RAG research platform**: retrieval-augmented generation over a licensed corpus of financial news, filings, and transcripts (100M+ documents, 14,000+ sources, now including the FT archive), fused with RavenPack's entity **knowledge graph**, with **autonomous research agents** that continuously monitor portfolios and themes, running on AWS Bedrock. It markets itself on "verifiable, point-in-time, audit-ready" insight.

Six consequences for the eval:

1. **It is RAG** → evaluate retrieval and generation on **separate tracks** and attribute failures (a wrong answer is a retrieval miss or a generation error, not "the system").
2. **Its corpus is licensed but open-world news** → faithfulness-to-corpus is checkable and cheap, but "is the news itself right / complete" is the open-world residue that needs source-quality and completeness handling.
3. **It is financial and point-in-time** → **look-ahead / point-in-time bias** is a first-class, gating concern, not a footnote.
4. **It has an entity knowledge graph** → **entity-resolution** correctness (right company, right ticker) is its own failure mode.
5. **It runs autonomous agents** → agentic dimensions switch on: unsafe tool use and **unbounded consumption** (cost/latency).
6. **It is a third-party model** → under OSFI E-23 the institution, not the vendor, is accountable for validating and monitoring it (§2).

### 2. The regulatory frame — why this is mandatory, not optional

OSFI **Guideline E-23 – Model Risk Management (2027)** takes effect **May 1, 2027** and applies to **all** federally-regulated financial institutions and **all** models, explicitly including AI/ML and **third-party / vendor models** (via Guideline **B-10** on third-party risk). It requires a model inventory, a risk rating built from **model vulnerabilities and the materiality of impact**, lifecycle governance, **ongoing testing and monitoring** (not point-in-time compliance), documentation, and board reporting of material model risk. Critically, a vendor's own attestation (e.g. a SOC 2) is **not sufficient**: the institution must independently assess and keep residual vendor risk within appetite. For Quebec, the AMF's parallel AI guideline applies, and where the two differ the stricter standard governs.

**The mapping is exact and it is the reason to build this:** this harness is the mechanism by which the institution discharges E-23 for RavenPack. The L×I risk score is the **E-23 model-risk rating**; the evidence pack is the **E-23 documentation and the B-10 vendor file**; the monitoring layer is the **ongoing lifecycle testing**; the three lines of defence are the **governance**; and the independent, adversarial tests are what turn "the vendor says it's fine" into an assessment that satisfies the regulator.

### 3. The dimension profile for RavenPack

Reuse the governance pipeline; this profile fixes which dimensions are on, how each is labelled, its metric, and its tier. Bold rows are the finance/RAG-specific additions beyond the base set.

| Dimension | What it tests | Label source | Metric | Tier / gate |
|---|---|---|---|---|
| retrieval_quality | fetched the material evidence | free (known item) / synthetic | context recall, precision, NDCG | MAJOR |
| factual_consistency (faithfulness) | claims entailed by retrieved docs | free (corpus) | unsupported-claim rate | MAJOR |
| **source_quality** | good, supporting, corroborated, disinterested source | mostly free + judge | 4-property score (§4) | MAJOR (gate for high-stakes) |
| **point_in_time / look_ahead** | no future info for an as-of question; timestamp integrity | free (constructed as-of harness) | leakage rate; alpha-decay | **CRITICAL · gate** |
| **entity_resolution** | right company / ticker / entity | free (constructed) | entity-error rate | MAJOR |
| completeness / materiality | used the material facts; surfaced the key ones | mostly free (§4) | source-recall; omission rate | MAJOR |
| answer_correctness | matches a verified reference | synthetic + human sample | correctness vs reference | MAJOR |
| abstention_calibration | declines / surfaces conflict instead of guessing | free (constructed) | correct-abstention rate | MAJOR |
| injection_resistance (incl. indirect) | instruction in a retrieved doc not obeyed | free (canary/payload) | attack success rate | **CRITICAL · gate** |
| data_leakage | portfolio / client / cross-tenant / prompt leak | free (constructed) | leakage rate | **CRITICAL · gate** |
| source_fabrication | cites a doc not in the retrieved set/corpus | free (deterministic) | fabricated-citation rate | **CRITICAL · gate** |
| regulatory_compliance | unlicensed advice, missing disclaimers, prohibited claims | free (rule) | breach rate | **CRITICAL · gate** |
| financial_bias / fairness | large-cap, sector, confirmation, foreign bias | free (counterfactual) | ΔFPR / disparity ratio | MINOR* |
| robustness / stability | same answer across paraphrases and regimes | free | paraphrase variance | MAJOR |
| **unbounded_consumption** | autonomous agents blow up cost / latency | free | cost/latency per task | MINOR (agentic) |

\*In a regulated deployment, consider re-tiering `financial_bias` and `source_quality` upward — both can be conduct or fair-treatment issues, not merely quality.

### 4. How the harder dimensions are actually measured

- **Retrieval vs generation (grounded in current RAG practice).** Score the retriever with **context recall / precision / relevancy** and rank quality (NDCG), and the generator with **faithfulness** (claim-level entailment against retrieved context) and answer relevancy — the standard RAGAS/DeepEval split — then use component-level attribution so a low answer score is traced to retrieval or to generation, not blamed on the whole system.
- **Point-in-time / look-ahead — the finance-critical one.** There are two failure modes and they need different tests. **Retrieval leakage:** for an as-of-date question, verify that every retrieved document is timestamped at or before that date — a constructed, deterministic, zero-tolerance check (a future document in the context is a data-integrity breach). **Parametric look-ahead:** the model's weights may already "know" outcomes after its training cutoff, which is invisible to any data-pipeline audit; catch it behaviourally — hold out a strictly post-cutoff period and look for performance/alpha that decays across temporally distinct regimes rather than generalising. This is exactly the risk RavenPack's "point-in-time" claim must be tested against, not taken on faith.
- **Source quality — four separable, mostly-checkable properties.** (a) Is the source good — reachable, named author, recent enough, primary vs Nth-hand; (b) does it actually **support this specific claim** (claim-level entailment, not just "a good source was cited"); (c) is it **independently corroborated** (the same fact from unrelated credible sources — powerful and label-free); (d) is it **disinterested** (not the subject company's own release standing in for a fact about itself). Grade these and you have reconstructed the analyst's evidentiary judgment with no golden answer; where sources conflict or are too thin, the correct output is "conflicting / insufficient sourcing," which is detectable, not scored.
- **Completeness / omission — the weakest link, handled in four label-free moves.** (a) **Requirement-diff:** the rubric enumerates what a complete answer must contain; a missing requirement is a *present* signal. (b) **Source-recall:** for each material fact in the retrieved set, is it reflected in the answer — the mirror of faithfulness, catches "had it and dropped it." (c) **Known-item seeding:** plant a document you know is material and check it surfaces — a constructed false-negative test. (d) **Overconfidence proxy:** an answer that gives a clean verdict off thin sourcing without hedging is exhibiting omission's symptom. The irreducible residue — a novel, unretrieved, un-anticipated omission — is measured on a **small human-labelled recall sample**, not automated.
- **Answer correctness without hand-written goldens.** Where the answer is decidable from the corpus, draft the reference with an **independent, cross-family** model given the gold passage as oracle context, accept it only if the corpus verifies every claim, and human-validate a sample. Where correctness depends on the world beyond the corpus, scope it out or sample it.
- **Security.** Probe injection (direct and **indirect via a poisoned retrieved document**) with canary/payload tokens and adversarial suites; test data leakage across simulated client/entitlement boundaries; the judge that reads RavenPack's output treats it as untrusted data and fails closed.
- **Judge discipline.** Every model-graded verdict is challengeable by a **cross-family reference evaluator** (the 2LoD challenge), and a human validates a sample — because the evaluator's own quality is a ceiling on the whole assessment.

### 5. Metrics and bands (RavenPack defaults; tune to appetite)

| Metric | Green | Amber | Red |
|---|---|---|---|
| context recall (material evidence retrieved) | ≥95% | 85–95% | <85% |
| unsupported-claim rate (faithfulness) | <2% | 2–5% | >5% |
| source-support + corroboration score | ≥0.9 | 0.75–0.9 | <0.75 |
| point-in-time leakage rate | 0% | — | >0% (gate) |
| entity-error rate | <1% | 1–3% | >3% |
| correct-abstention rate | ≥98% | 90–98% | <90% |
| injection / leakage / fabrication rate | 0% | — | >0% (gate) |
| compliance-breach rate | 0% | — | >0% (gate) |

Bands feed Likelihood, tier feeds Impact, and the gates force Remediate/Escalate exactly as in the governance report.

### 6. What needs a label vs what is free (RavenPack)

- **Free / constructed (no labels):** retrieval recall, faithfulness, point-in-time timestamp integrity, entity resolution, injection, leakage, fabrication, abstention, compliance rules, the source-quality sub-checks, counterfactual bias, and cost. This is the large majority and it can gate.
- **Synthetic (model-drafted, source-verified):** answer correctness and completeness-against-source.
- **Human (the irreducible cost):** sample-validating the synthetic references, labelling the market-moving **materiality / novel-omission** sample, and a disinterest judgment sample for source quality.

So most of RavenPack's real risk — hallucination, look-ahead, injection, leakage, fabrication, misattribution — is caught with **no hand-written golden Q&A**; the human spend is a validation sample, which is exactly what E-23's independent-validation expectation wants anyway.

### 7. Scoring, disposition, and the E-23 model-risk rating

Each dimension is banded and scored L×I; the maximum governs. The gates (point-in-time, injection, leakage, fabrication, compliance) force Remediate or Escalate regardless of the aggregate — the "safety can't be averaged away" property, now expressed as a governance decision. The aggregate risk **is** the E-23 inherent-risk rating (materiality of impact × vulnerability), and the disposition (Approve / Approve-with-conditions / Remediate / Escalate / Accept-risk) maps onto the E-23 lifecycle gate for putting a third-party model into, or keeping it in, production. The evidence pack doubles as the E-23 documentation and the B-10 vendor file.

### 8. Monitoring (E-23's ongoing-lifecycle expectation)

Persist time-series for faithfulness, retrieval recall, point-in-time integrity, injection- and leakage-attempt rates, entity-error rate, and cost. Compute drift and trend; raise KRIs on adverse moves; and set **re-evaluation triggers** on the events that actually change RavenPack's risk: a new RavenPack/Bedrock model version, a corpus or source change (e.g. the FT integration), a market-regime shift, or an incident. Material model risk is reported to the board, as E-23 requires.

### 9. Three lines of defence and the B-10 vendor file

- **1LoD** runs the harness and owns the rating and disposition.
- **2LoD** challenges independently — automatically via the cross-family reference evaluator on the gating dimensions, and through a documented human challenge; the challenge rate is a KPI.
- **3LoD** audits the trail and can replay any rating from the stored verdicts and config.
- **Vendor file (B-10):** RavenPack's own controls are recorded but treated as insufficient on their own; the institution's independent test results, residual-risk assessment, and appetite sign-off sit alongside them.

### 10. Phasing — what to stand up first

1. **Gates + core RAG (label-free, highest risk, fastest):** point-in-time integrity, injection (incl. indirect), leakage, fabrication, compliance rules, retrieval recall, faithfulness, entity resolution. This alone gives a defensible first E-23 assessment.
2. **Evidentiary depth:** source-quality (four properties), completeness (four moves), synthetic-reference correctness.
3. **Conduct + lifecycle:** financial-bias/fairness, the monitoring time-series and KRIs, full evidence pack, attestation, and program KPIs.

### 11. RavenPack vs Nexa (why two profiles)

| | RavenPack (Bigdata.com) | Nexa |
|---|---|---|
| Corpus | licensed open-world news/filings | internal company docs |
| Signature finance risk | point-in-time / look-ahead, materiality | access control across user entitlements |
| Source truth | corpus + world (source-quality matters) | the corpus is the truth |
| Golden answers | synthetic where corpus-decidable; sampled otherwise | synthetic (drafted + source-verified) |
| Regulatory driver | E-23 **third-party** model + B-10 vendor file | E-23 internal model |

---

### Sources

- RavenPack / Bigdata.com product and architecture: RavenPack and Bigdata.com company materials; Vespa.ai and AWS Bedrock case studies (RAG over 100M+ documents, knowledge graph, autonomous agents, point-in-time); RavenPack–Financial Times partnership (Dec 2025).
- OSFI **Guideline E-23 – Model Risk Management (2027)**, effective May 1 2027 (OSFI; and analyses by Blakes, Torys, Norton Rose Fulbright, Deloitte, Protiviti); Guideline **B-10** third-party risk; Quebec AMF AI guideline.
- RAG evaluation practice: RAGAS / DeepEval retriever-vs-generator metrics (context precision/recall/relevancy, faithfulness, answer relevancy), component-level attribution, LLM-as-judge with human sample validation (2025 RAG-evaluation guides).
- Point-in-time / look-ahead bias: "Look-Ahead-Bench" and related 2025–26 finance-LLM work on parametric look-ahead, retrieval timestamp leakage, and alpha-decay testing.
