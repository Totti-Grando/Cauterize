Per corpus (once):   embed all chunks → store vectors;  build BM25 inverted index
Per claim:
  claim → BM25 lookup      → top-k₁ chunks   (exact terms)
  claim → embed + cosine   → top-k₂ chunks   (paraphrase)
  candidates = unique(k₁ ∪ k₂)              ← union protects recall
  order candidates by score
  for each candidate (best first):
      DeBERTa entails(chunk, claim)          ← the real decision
      if Entailment ≥ τ: grounded, STOP      ← short-circuit
  else: not grounded (→ bare claim / derived-claim path)
Batch the DeBERTa calls across claims where you can.


Response Quality (4)

┌──────────────┬───────┬─────────────┬─────────────┐
│  dimension   │ tier  │ eval method │  gates on   │
├──────────────┼───────┼─────────────┼─────────────┤
│ accuracy     │ major │ llm_judge   │ fabrication │
├──────────────┼───────┼─────────────┼─────────────┤
│ relevance    │ major │ llm_judge   │ —           │
├──────────────┼───────┼─────────────┼─────────────┤
│ completeness │ major │ llm_judge   │ —           │
├──────────────┼───────┼─────────────┼─────────────┤
│ task_success │ major │ llm_judge   │ —           │
└──────────────┴───────┴─────────────┴─────────────┘

Evidence & Truthfulness (4)

┌────────────────────┬───────┬──────────────┬────────────────────────────────────┐
│     dimension      │ tier  │ eval method  │              gates on              │
├────────────────────┼───────┼──────────────┼────────────────────────────────────┤
│ hallucination      │ major │ source_check │ invented_policy, fabricated_source │
├────────────────────┼───────┼──────────────┼────────────────────────────────────┤
│ groundedness       │ major │ nli          │ —                                  │
├────────────────────┼───────┼──────────────┼────────────────────────────────────┤
│ source_quality     │ major │ source_fetch │ —                                  │
├────────────────────┼───────┼──────────────┼────────────────────────────────────┤
│ source_attribution │ major │ source_fetch │ —                                  │
└────────────────────┴───────┴──────────────┴────────────────────────────────────┘

Reasoning (3)

┌──────────────────────┬───────┬─────────────┬──────────┐
│      dimension       │ tier  │ eval method │ gates on │
├──────────────────────┼───────┼─────────────┼──────────┤
│ uncertainty_handling │ major │ llm_judge   │ —        │
├──────────────────────┼───────┼─────────────┼──────────┤
│ logical_consistency  │ major │ llm_judge   │ —        │
├──────────────────────┼───────┼─────────────┼──────────┤
│ assumption_quality   │ minor │ llm_judge   │ —        │
└──────────────────────┴───────┴─────────────┴──────────┘

Instruction Following (3)

┌───────────────────────┬───────┬───────────────┬──────────────────────┐
│       dimension       │ tier  │  eval method  │       gates on       │
├───────────────────────┼───────┼───────────────┼──────────────────────┤
│ constraint_compliance │ major │ llm_judge     │ constraint_violation │
├───────────────────────┼───────┼───────────────┼──────────────────────┤
│ format_compliance     │ minor │ deterministic │ —                    │
├───────────────────────┼───────┼───────────────┼──────────────────────┤
│ persona_compliance    │ minor │ llm_judge     │ —                    │
└───────────────────────┴───────┴───────────────┴──────────────────────┘

Safety (3)

┌─────────────────┬──────────┬─────────────┐
│    dimension    │   tier   │ eval method │
├─────────────────┼──────────┼─────────────┤
│ harmfulness     │ critical │ llm_judge   │
├─────────────────┼──────────┼─────────────┤
│ toxicity        │ critical │ llm_judge   │
├─────────────────┼──────────┼─────────────┤
│ refusal_quality │ critical │ llm_judge   │
└─────────────────┴──────────┴─────────────┘

Fairness (2)

┌──────────────┬───────┬─────────────┐
│  dimension   │ tier  │ eval method │
├──────────────┼───────┼─────────────┤
│ bias         │ major │ llm_judge   │
├──────────────┼───────┼─────────────┤
│ stereotyping │ major │ llm_judge   │
└──────────────┴───────┴─────────────┘

Communication (4)

┌───────────────┬───────┬─────────────┐
│   dimension   │ tier  │ eval method │
├───────────────┼───────┼─────────────┤
│ clarity       │ minor │ llm_judge   │
├───────────────┼───────┼─────────────┤
│ structure     │ minor │ llm_judge   │
├───────────────┼───────┼─────────────┤
│ conciseness   │ minor │ llm_judge   │
├───────────────┼───────┼─────────────┤
│ actionability │ minor │ llm_judge   │
└───────────────┴───────┴─────────────┘

Privacy & Security (4)

┌────────────────────────────┬──────────┬────────────────────┬─────────────────┐
│         dimension          │   tier   │    eval method     │    gates on     │
├────────────────────────────┼──────────┼────────────────────┼─────────────────┤
│ confidential_data_exposure │ critical │ injection_detector │ —               │
├────────────────────────────┼──────────┼────────────────────┼─────────────────┤
│ pii_leakage                │ critical │ injection_detector │ —               │
├────────────────────────────┼──────────┼────────────────────┼─────────────────┤
│ prompt_leakage             │ critical │ injection_detector │ —               │
├────────────────────────────┼──────────┼────────────────────┼─────────────────┤
│ security_compliance        │ major    │ llm_judge          │ insecure_advice │
└────────────────────────────┴──────────┴────────────────────┴─────────────────┘

Robustness (4)

┌─────────────────────────────┬──────────┬────────────────────┐
│          dimension          │   tier   │    eval method     │
├─────────────────────────────┼──────────┼────────────────────┤
│ prompt_injection_resistance │ critical │ injection_detector │
├─────────────────────────────┼──────────┼────────────────────┤
│ jailbreak_resistance        │ critical │ injection_detector │
├─────────────────────────────┼──────────┼────────────────────┤
│ paraphrase_stability        │ major    │ llm_judge          │
├─────────────────────────────┼──────────┼────────────────────┤
│ adversarial_robustness      │ major    │ llm_judge          │
└─────────────────────────────┴──────────┴────────────────────┘

RAG Quality (4)

┌─────────────────────┬───────┬─────────────┐
│      dimension      │ tier  │ eval method │
├─────────────────────┼───────┼─────────────┤
│ retrieval_precision │ major │ llm_judge   │
├─────────────────────┼───────┼─────────────┤
│ retrieval_recall    │ major │ llm_judge   │
├─────────────────────┼───────┼─────────────┤
│ context_utilization │ major │ llm_judge   │
├─────────────────────┼───────┼─────────────┤
│ context_relevance   │ major │ llm_judge   │
└─────────────────────┴───────┴─────────────┘

Agentic-only — retained, outside the §1 taxonomy (2)

┌───────────────────────┬──────────┬────────────────────┐
│       dimension       │   tier   │    eval method     │
├───────────────────────┼──────────┼────────────────────┤
│ unsafe_tool_use       │ critical │ injection_detector │
├───────────────────────┼──────────┼────────────────────┤
│ unbounded_consumption │ minor    │ deterministic      │
└───────────────────────┴──────────┴────────────────────┘
