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
