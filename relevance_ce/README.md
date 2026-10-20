# Claim–question relevance cross-encoder

A 9-class cross-encoder that scores how relevant each short claim is to a question, and says why
(DIRECT, PARTIAL, CONTEXT, WRONG_TIME, WRONG_INTENT, WRONG_RELATION, ECOSYSTEM, UNRESOLVED,
IRRELEVANT). Ettin 150M, fine-tuned on the RTX 5080 and served as int8 ONNX on CPU
(~1.6 s for 40 claims on 2 cores). Distilling to a smaller student is optional, for throughput only.

## Setup (5080 machine)

```
pip install torch --index-url https://download.pytorch.org/whl/cu128
pip install -r requirements.txt
python -c "import torch; print(torch.cuda.get_device_name(0), torch.cuda.get_device_capability(0))"   # expect (12, 0)
```

Serving machine only needs: `pip install onnxruntime transformers numpy`

## Run order

```
# 0. data (see data/CATALOG.md for what is ready and what is TODO)
python generate_synthetic.py --n_questions 12000 --out data/synthetic.jsonl   # included: 112,295 pairs
python paraphrase_synthetic.py --in data/synthetic.jsonl --out data/synthetic_para.jsonl   # REQUIRED: breaks template tells
python fetch_public.py --inspect                                              # check schemas first
python fetch_public.py --sources tempreason hotpotqa                          # Hugging Face sources
python fetch_public.py --sources twowiki --twowiki_dir raw/2wiki              # after downloading data.zip
python fetch_public.py --sources musique --musique_dir raw/musique            # after downloading MuSiQue
python label_real.py --in data/real_pairs.jsonl --out data/labeled_real.jsonl --second_pass 0.10
python label_real.py --in data/holdout_pairs.jsonl --out data/holdout.jsonl --holdout
python label_real.py --apply_adjudication data/holdout.disagreements.csv --out data/holdout.jsonl
#    wire your extractor into tagger_hook.py so public/paraphrased rows get the same tags as real rows
python build_dataset.py      # -> data/mix/mix.jsonl, data/mix/manifest.json, data/CATALOG.md

# 1. teacher (check the "init:" line says CrossEncoder ... head layers copied)
python train_teacher.py --data data/mix/mix.jsonl \
    --init cross-encoder/ettin-reranker-150m-v1 --out runs/teacher-150m
python score.py --model runs/teacher-150m --eval data/holdout.jsonl --split test   # the scorecard that counts

# 2. baseline for the NDCG@5 gate
python baseline_zero_shot.py --data data/labeled_real.jsonl --split test

# 3. OPTIONAL: smaller student, only if throughput becomes the constraint
python distill_student.py --teacher runs/teacher-150m \
    --data data/synthetic.jsonl data/labeled_real.jsonl --unlabeled data/unlabeled_real.jsonl \
    --init cross-encoder/ettin-reranker-32m-v1 --out runs/student-32m

# 4. export + gates (the 150M itself)
python export_onnx.py --model runs/teacher-150m --out deploy/model-150m
python score.py --model deploy/model-150m --check_against runs/teacher-150m
python score.py --model deploy/model-150m --bench 200
python score.py --model deploy/model-150m --eval data/labeled_real.jsonl --split test
python score.py --model deploy/model-150m --demo
```

## Row format (all data files)

```json
{"qid": "real-000123", "question": "...", "q_tags": "[ENT] Name:ORG [TIME] 2026Q2 [ATTR] net_flows",
 "claim": "...", "c_tags": "[ENT] Name:ORG=MATCH [TIME] 2026Q2 [ATTR] net_flows",
 "label": "PARTIAL", "split": "train", "weight": 1.0}
```

Link statuses in `c_tags`: MATCH, ALIAS, ADJACENT, UNRESOLVED, NONE. Periods: `2026Q2`, `FY2025`,
`2024-03`, or `NONE`. Split by entity or question cluster, never by row.

## Using it

```python
from score import Scorer
s = Scorer("deploy/model-150m")
for r in Scorer.ranked(s.score(question, q_tags, [(claim, c_tags), ...])):
    print(r["relevance"], r["label"], r["confidence"], r["uncertain"], r["gate"], r["claim"])
```

Each claim's answer is its most likely class (`label`), and `relevance` is that class's utility
tier (DIRECT 1.00, PARTIAL 0.70, CONTEXT 0.40, ... IRRELEVANT 0.00). `confidence` is the model's
probability for that class; claims under 0.5 are flagged `uncertain`. `probs` shows all nine.
`Scorer.ranked()` sorts by tier, then confidence within a tier. Two symbolic gates can move a
label down, never up: a confident period mismatch → WRONG_TIME, an unresolved entity →
UNRESOLVED. When a gate fires, `model_label` keeps what the model said. Utilities live in
`common.py` and each model's `meta.json`; changing them re-tiers without retraining.

## Status

Tested end to end on CPU with tiny random local models: synthetic generation, assembly, training,
distillation, ONNX/int8 export and gated scoring. Converters in `fetch_public.py` were tested on
fixture rows built to each dataset's documented format; run `--inspect` on the real downloads first,
since Dropbox and Hugging Face were unreachable from the build environment. `label_real.py` and
`paraphrase_synthetic.py` were tested with a mocked API client, not live calls. Not yet run against
real Ettin checkpoints; that is phase 0 on the 5080.
