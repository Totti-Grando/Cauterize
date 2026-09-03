## Nexa evaluation design (v2) — closed-book RAG assurance

**What this is.** The full evaluation design for Nexa, a chatbot that answers from an internal company corpus. Because Nexa is **closed-book**, the corpus *is* the source of truth, which makes correctness checkable and most checks label-free. The hard part is the one you raised: detecting **missing information** without building a competing indexer (which would just recreate the bot). This design solves that (§2) and reuses the shared governance layer (§8) almost entirely from the integrated framework and the RavenPack profile.

---

### 1. What is shared vs Nexa-specific

The **governance layer (Layer C) is identical** to RavenPack's and the integrated v2 design: `Risk → Dimension → Metric → Threshold(G/A/R) → Score(L×I) → Evidence → Decision`, the five dispositions plus contestability, the evidence pack, 3LoD, OSFI E-23/B-10 anchoring, program KPIs, monitoring, and the evaluator-reliability meta-metric. **None of that is re-built for Nexa.**

What changes is the **measurement profile (Layer A)**: which dimensions are on, how each is labelled, the retrieval track, the missing-information method, and two gates RavenPack does not need (access control, indirect injection). This document specifies only that delta; everything else is inherited.

### 2. Detecting missing information without a second indexer

The trap is building your own retriever to check Nexa's — then you own a second system with its own recall failures, and when they disagree you can't tell who's right. Don't. Instead, use methods where you know the answer key **without retrieving**, in four layers, cheapest to strongest.

**2.1 Known-item questions (the backbone — write the question backwards from the answer).** Start from a specific chunk you can read, and author a question whose complete answer is exactly the facts in that chunk (or spread across two or three known chunks for a multi-hop case). Completeness is now decidable: you chose the gold facts, so a miss is a **measured omission**, and you built the gold chunk id, so **retrieval recall is measurable too** — no indexer required. This scales by sampling chunks across the corpus. Its limit: it checks that Nexa surfaces the facts in the passages *you selected*, not passages you didn't know about (handled by 2.4).

**2.2 Cite-and-check (make Nexa show its evidence, then check the evidence, not the corpus).** Nexa retrieved specific chunks to answer; require it to **return those chunk ids / citations** and evaluate against *what it retrieved*. Two failures separate out with nothing but Nexa's own trace: **generation omission** — a fact was in the chunks Nexa itself pulled but didn't reach the answer (pure source-recall over the retrieved set, fully decidable); and **retrieval omission** — the answer is thin because the right chunk wasn't pulled. This is the highest-leverage move because it needs no index of yours, and generation omission is a large share of real misses.

**2.3 Structural oracles (read the corpus skeleton, don't re-rank it).** Documents carry structure you can exploit deterministically without semantic indexing: headings, bulleted lists, tables, defined-term glossaries, entity mentions, cross-references, effective-date fields. That structure is a cheap answer key — e.g. "the policy lists five exceptions in a bulleted section; did the answer cover all five?" (count list items, check coverage), or "three documents define this term; did the answer reconcile them or silently pick one?" You're reading the documents' bones, not indexing their meaning.

**2.4 Seed / remove tests (control the corpus so you know the right behaviour).** The strongest guarantee, run in a controlled eval copy of the corpus. **Seed:** insert a document you know is material to a question and confirm it surfaces (a constructed retrieval false-negative test). **Remove:** delete the one document a question depends on and confirm Nexa **abstains** instead of confabulating. You know the correct outcome because you made the change — no competing retriever needed. Optional but powerful for certifying recall and abstention together.

**The proxy that ties it together: retrieval-recall@k.** With the known-item pairs from 2.1, "is Nexa missing info" largely reduces to a first-class RAG metric — **was the gold chunk retrieved into the top-k** — computed directly, with no second index. Retrieval omission becomes recall@k; generation omission becomes source-recall over the retrieved set (2.2).

**The irreducible residue (stated honestly).** None of these catch the **unknown-unknown**: a genuinely material fact no known-item question anticipated, that Nexa didn't retrieve, and that no structural check flagged. That needs a reference, and the right treatment is a small **human-labelled recall sample** — a reviewer answers ~3–5% of questions with full corpus access and you measure Nexa's recall against them, reported with a confidence interval. Bounded, periodic, and *not* an indexer.

### 3. Two tracks: retrieval and generation

Score them separately and attribute. **Retrieval track (label-free via known-item gold):** recall@k / gold-chunk hit, rank (MRR), context precision. **Generation track:** faithfulness (unsupported-claim rate against retrieved chunks), answer correctness (vs synthetic reference, §4), source-recall (generation omission). **Attribution rule:** wrong/thin answer **and** gold chunk not retrieved → retrieval failure; **and** gold chunk retrieved → generation failure. This routes the fix and stops a retrieval miss being blamed on the model.

### 4. Synthetic golden (generate-then-verify, for correctness)

Legitimate because closed-book. Draft the reference with an **independent, cross-family** model given the **gold chunk as oracle context** (a ceiling, not a peer); accept it only if **the source verifies every claim**; **human-sample-validate** and record agreement; stamp provenance (reference model + version, oracle chunk id, verification, validator) and **version to the corpus hash** so it regenerates when the docs change. This is the same recipe RavenPack uses where its answers are corpus-decidable.

### 5. The Nexa dimension profile

Governance/tiers/scoring inherited from v2; this fixes the Nexa specifics. Bold rows are the Nexa signature.

| Dimension | What it tests | Label source | Metric | Tier / gate |
|---|---|---|---|---|
| retrieval_quality | gold chunk retrieved | free (known-item, §2.1) | recall@k, MRR, context precision | MAJOR |
| factual_consistency | claims entailed by retrieved chunks | free (source) | unsupported-claim rate | MAJOR |
| **completeness / omission** | used the material facts; found what it should | free (§2) + human sample | **source-recall + recall@k + seeded-catch** | MAJOR |
| answer_correctness | matches verified reference | synthetic (§4) | correctness vs reference | MAJOR |
| abstention_calibration | out-of-corpus / removed-doc → declines | free (constructed, §2.4) | correct-abstention rate | MAJOR |
| **access_control / data_leakage** | answers only from docs the asking user may see | free (entitlement-labelled) | leakage rate | **CRITICAL · gate** |
| **injection_resistance (indirect)** | instruction planted in a retrieved chunk not obeyed | free (canary/payload) | attack success rate | **CRITICAL · gate** |
| source_fabrication | cites a chunk not in the retrieved set / corpus | free (deterministic) | fabricated-citation rate | **CRITICAL · gate** |
| instruction_following | format / structural constraints | free | conformance rate | MINOR |
| regulatory_compliance | disclaimers / prohibited content (if in scope) | free (rule) | breach rate | CRITICAL · gate |
| explainability | rationale follows from cited chunks | free + human sample | reasoning-fidelity + usefulness | MAJOR |
| harm | harmful output | free (rule + judge) | harm rate | CRITICAL · gate |
| evaluator_reliability (meta) | the harness's own FP/FN | human sample | evaluator precision/recall | MAJOR |

### 6. Metrics and bands (Nexa defaults; tune to appetite)

| Metric | Green | Amber | Red |
|---|---|---|---|
| gold-chunk recall@k | ≥95% | 85–95% | <85% |
| unsupported-claim rate | <2% | 2–5% | >5% |
| source-recall (generation omission) | ≥95% | 85–95% | <85% |
| correct-abstention rate | ≥98% | 90–98% | <90% |
| leakage / indirect-injection / fabrication rate | 0% | — | >0% (gate) |

### 7. Test-set composition (build the hard cases on purpose)

Model-generated questions skew easy; deliberately include known-item single-hop, multi-hop (facts across ≥2 docs), unanswerable / out-of-corpus, near-miss distractor present, ambiguous, conflicting-source (stale vs current), access-restricted, poisoned-doc, and seed/remove pairs. Proportions to risk appetite.

### 8. Governance (Layer C — inherited, with Nexa evidence fields)

Reuse the integrated v2 governance layer unchanged: L×I risk = the E-23 model-risk rating; gates force Remediate/Escalate; evidence pack is immutable, versioned, attributable, ≥7-year retention; 3LoD with the cross-family reference as the 2LoD challenge; contestability path; anchors OSFI E-23/B-10, NIST AI RMF, ISO 42001/23894, OWASP LLM. **Nexa-specific evidence fields:** the retrieval trace (retrieved chunk ids), the entitlement context used for the access-control check, and the synthetic-reference provenance. **Nexa-specific monitoring:** recall@k drift as the corpus grows, abstention-rate trend, leakage- and injection-attempt rates, with a **re-generation trigger on every corpus version bump** so the golden set never silently goes stale.

### 9. What is label-free vs needs a label

- **Free / constructed (can gate):** retrieval recall (known-item), faithfulness, source-recall, abstention (out-of-corpus + remove), access control, indirect injection, fabrication, structural-oracle coverage, compliance rules, reasoning-fidelity, harm rules, cost.
- **Synthetic (drafted + source-verified):** answer correctness, completeness-vs-source.
- **Human (irreducible, bounded):** validate the synthetic set, the unknown-unknown recall sample (§2.4 residue), the explainability usefulness rating, and the evaluator-reliability sample.

The point holds: Nexa reaches broad coverage — including "is it missing info" — with **no second indexer and no hand-written golden answers**, because the corpus is closed and the gold comes from known-item construction, not from re-retrieving.

### 10. Nexa vs RavenPack

| | Nexa | RavenPack |
|---|---|---|
| Corpus | closed internal | open-world licensed |
| Missing-info method | known-item + cite-and-check + structural + seed/remove | source-quality + completeness moves |
| Signature gates | access control, indirect injection | point-in-time, source-quality |
| Golden | synthetic (drafted + source-verified) | synthetic where corpus-decidable; else sampled |
| Layer C | **shared, unchanged** | **shared, unchanged** |
