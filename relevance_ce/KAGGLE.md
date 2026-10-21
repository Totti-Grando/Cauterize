# Training relevance_ce on a free Kaggle GPU

Kaggle gives a free T4/P100 (30 GPU-hours/week, no credit card). This whole run
(regenerate synthetic data → build mix → fine-tune Ettin 150M → export int8 ONNX)
finishes in one session, then the model is pushed back here via Git LFS.

Neither the T4 nor the P100 supports bf16, so `train_teacher.py` auto-falls back to
fp32 on them (see the `amp_dtype` guard). It prints `amp: off (fp32)` — expected.

## One-time account setup
1. Create a kaggle.com account and **verify your phone** (Settings → Phone Verification).
   This unlocks GPU + internet in notebooks.
2. New Notebook → right-hand panel:
   - **Accelerator** → `GPU T4 x2` (or `GPU P100`)
   - **Internet** → `On`  (needed for pip, HuggingFace, and git push)

## Store a GitHub token (for private clone + LFS push)
1. GitHub → Settings → Developer settings → **Fine-grained token**, repo
   `Totti-Grando/Cauterize`, permission **Contents: Read and write**. Copy it.
2. In the Kaggle notebook: **Add-ons → Secrets → Add secret**
   - Label: `GH_TOKEN`  Value: *(paste the token)*
   - (optional) Label: `GH_USER` Value: your GitHub username

## The notebook — paste each block into its own cell

### Cell 1 — secrets + git-lfs
```python
from kaggle_secrets import UserSecretsClient
s = UserSecretsClient()
import os
os.environ["GH_TOKEN"] = s.get_secret("GH_TOKEN")
os.environ["GH_USER"]  = "Totti-Grando"   # repo owner; change if you forked
!apt-get -qq install -y git-lfs >/dev/null 2>&1; git lfs install
```

### Cell 2 — clone the branch
```python
import os
url = f"https://{os.environ['GH_TOKEN']}@github.com/Totti-Grando/Cauterize.git"
!git clone --branch feature/relevance-ce --single-branch {url} /kaggle/working/Cauterize
%cd /kaggle/working/Cauterize/relevance_ce
!git config user.email "kaggle@local"; git config user.name "kaggle-runner"
```

### Cell 3 — dependencies (Kaggle already ships CUDA torch; don't reinstall it)
```python
!pip -q install "transformers>=4.51" "sentence-transformers>=5.5" datasets onnx onnxruntime onnxscript anthropic
import torch; print("torch", torch.__version__, "cuda", torch.cuda.is_available(),
                    "| device", torch.cuda.get_device_name(0))
```

### Cell 4 — regenerate synthetic data + fetch real public data (HotpotQA)
```python
!python generate_synthetic.py --n_questions 12000 --out data/synthetic.jsonl
!python fetch_public.py --sources hotpotqa      # real data, converter verified on live schema
!python build_dataset.py                        # folds HotpotQA in, capped at 20% of train
```
HotpotQA covers DIRECT/PARTIAL/WRONG_INTENT/IRRELEVANT (the other 5 classes stay synthetic).
TempReason is skipped: its HF default lacks `fact_context` and yields 0 rows (needs L2/L3 files).

### Cell 5 — fine-tune the teacher (prints `amp: off (fp32)` on T4/P100)
```python
!python train_teacher.py --data data/mix/mix.jsonl \
    --init cross-encoder/ettin-reranker-150m-v1 --out runs/teacher-150m
```

### Cell 6 — score + export int8 ONNX
```python
!python score.py --model runs/teacher-150m --eval data/mix/mix.jsonl --split test
!python export_onnx.py --model runs/teacher-150m --out deploy/model-150m
!python score.py --model deploy/model-150m --check_against runs/teacher-150m
!python score.py --model deploy/model-150m --bench 200
```

### Cell 7 — push the trained model back through Git LFS (int8 only, to respect the 1 GB LFS cap)
```python
# push only what you serve; skip the ~600 MB fp32 model.onnx to stay under free LFS quota.
# Each !command must be ONE line — no backslash continuations (Jupyter parses them as Python).
!cd /kaggle/working/Cauterize && git add -f relevance_ce/deploy/model-150m/model.int8.onnx relevance_ce/deploy/model-150m/meta.json relevance_ce/deploy/model-150m/report.json relevance_ce/deploy/model-150m/tokenizer
!cd /kaggle/working/Cauterize && git commit -m "Kaggle run: trained + exported teacher-150m (synthetic + hotpotqa)"
!cd /kaggle/working/Cauterize && git push origin HEAD:feature/relevance-ce
```
If this fails with an LFS over-quota error, don't retrain — the model is saved in the Kaggle
**version Output** (`Cauterize/relevance_ce/deploy/model-150m/`); download it from there instead.

## Back on your machine
```bash
git pull
git lfs pull                       # downloads the model blobs
```
Then serve on CPU — no CUDA needed:
```python
from score import Scorer
s = Scorer("relevance_ce/deploy/model-150m")
```

## Notes
- This run is **synthetic-only** — it validates the full stack on real Ettin weights
  and gives a first scorecard, but is not the shippable model. For that, add
  `paraphrase_synthetic.py` + `label_real.py` (both need `ANTHROPIC_API_KEY`) and wire
  your extractor into `tagger_hook.py`.
- GitHub free LFS is 1 GB storage / 1 GB bandwidth per month; the int8 model is ~150 MB.
- If a Kaggle session times out (idle), re-run cells 1–2 then continue; `runs/` is lost
  on disconnect unless you enable "Persistence" or save outputs, so run cells 4–7 in one go.
