# Claim graph + retrieve-then-verify grounding — integration guide

This bundles three things so they can be lifted onto another machine:

1. **Claim graph** — a deterministic, no-model visualization of claim/check/source/dimension nodes
   and their relationships, with the special cases (AND-gates, soft/OR-ish siblings, orphans) made
   first-class.
2. **Grounding + source-attribution scoring** — per-claim truthfulness bound by NLI entailment
   against the source documents.
3. **Local DeBERTa NLI model** — the entailment engine, shipped as a GitHub Release asset (git can't
   hold ~360 MB).

## Layout

| Piece | File |
| --- | --- |
| Claim-graph builder + standalone HTML renderer | `aah/api/claim_graph.py` |
| Nodal claim scoring (per-node truthfulness rollups) | `aah/api/claim_scoring.py` |
| Per-claim extraction + binding grounding/attribution | `aah/api/claim_extraction.py` |
| Hybrid retrieve-then-verify (BM25 ∪ spaCy dense → NLI) | `aah/api/claim_retrieval.py` |
| Local transformer NLI (DeBERTa) | `aah/api/local_nli.py` |
| Model download helper | `scripts/fetch_model.py` |
| Tests | `tests/test_claim_graph.py`, `test_claim_scoring.py`, `test_claim_extraction.py`, `test_claim_retrieval.py`, `test_local_nli.py` |

Endpoints (`aah/api/server.py`): `GET /api/graph[.html]`, `GET /api/claim-tree[.html]`,
`POST /api/claim-tree/extract[.html]` (`grounding="retrieval"` uses the pipeline below).

## The grounding pipeline (retrieve-then-verify)

Per corpus (once): embed all chunks → store vectors; build the BM25 inverted index.

Per claim:

```
claim → BM25 lookup     → top-k₁ chunks   (exact terms / numbers / tickers)
claim → embed + cosine  → top-k₂ chunks   (paraphrase, via spaCy en_core_web_lg)
candidates = unique(k₁ ∪ k₂)              ← RRF fusion; union protects recall
order candidates by fused score
for each candidate (best first):
    DeBERTa entails(chunk, claim)         ← the real decision
    if Entailment ≥ τ: grounded, STOP     ← short-circuit
else: not grounded → bare-claim / derived-claim path
```

DeBERTa calls are **batched across claims** at each rank (`verify_grounding` in
`claim_retrieval.py`). Grounding retrieves over **all** sources; **attribution** retrieves within the
**cited** source only (citation clause stripped first so grounding judges the fact, attribution the
source). Model: `MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli`.

## Getting the model onto a new machine (HuggingFace-blocked friendly)

The weights ship as a Release asset — no HuggingFace, no `gh`, no auth (public repo):

```bash
cd Agentic_Eval
python scripts/fetch_model.py            # downloads + sha256-verifies + unzips into models/
```

This lands the four files (`config.json`, `model.safetensors`, `tokenizer.json`,
`tokenizer_config.json`) in `models/deberta-mnli-fever-anli/`. Then point the harness at it offline:

```bash
export AAH_NLI_MODEL="$(pwd)/models/deberta-mnli-fever-anli"
export HF_HUB_OFFLINE=1
# Intel-GPU box only:
export AAH_NLI_DEVICE=xpu
```

Python deps for the local path install from PyPI (not HF-blocked): `transformers`, `torch`
(`+cu128` for Blackwell/RTX-50xx, `+xpu`/`ipex` for Intel), `sentencepiece`, `protobuf`, `spacy`
plus the `en_core_web_lg` package (spaCy's own CDN, HF-free).

Release: **`nli-model-v1`** on `Totti-Grando/Cauterize` · asset `deberta-mnli-fever-anli.zip`
· sha256 `7cb2554497a461ee171e50589362a6b624d96c33c5984fb55196bd3ef508831c`.

## Verify

```bash
.venv/Scripts/python.exe -m pytest tests/test_claim_graph.py tests/test_claim_scoring.py \
  tests/test_claim_extraction.py tests/test_claim_retrieval.py tests/test_local_nli.py -q
```

The pure-transform + retrieval tests run with **no** model. The `local_nli` tests that need weights
skip automatically when the model dir is absent, so run `scripts/fetch_model.py` first for full
coverage.
