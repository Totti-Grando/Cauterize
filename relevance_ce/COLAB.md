# Training relevance_ce on a free Google Colab GPU

Colab gives a free T4 (separate from Kaggle's quota). This run = regenerate synthetic data +
fetch real HotpotQA + fine-tune Ettin 150M + export int8 ONNX, then push back via Git LFS.
T4 has no bf16, so `train_teacher.py` falls back to fp32 (prints `amp: off (fp32)`), ~30-50 min
for 1 epoch.

## Setup (before running any cell)
1. **Runtime → Change runtime type → T4 GPU → Save.**
2. **Secrets** (🔑 icon, left sidebar) → **Add new secret**:
   - Name `GH_TOKEN`, value = your fine-grained GitHub token (Contents: Read **and write** on
     `Totti-Grando/Cauterize`). Toggle **Notebook access** on.
   - (If you skip this, Cell 1 falls back to prompting you for the token.)

## ⚠️ Free Colab has no headless/commit mode
Unlike Kaggle's "Save & Run All", a free Colab session dies on idle (~90 min) or if you close the
tab. So: **keep the tab open and the computer awake** during the run, and **run Cell 6b (Drive
backup) before Cell 7** — that way the model survives even if the push fails or the session drops.

## Cells (paste each into its own cell, run top to bottom)

### Cell 1 — token + git-lfs
```python
import os, getpass
try:
    from google.colab import userdata
    os.environ["GH_TOKEN"] = userdata.get("GH_TOKEN")
except Exception:
    os.environ["GH_TOKEN"] = getpass.getpass("GitHub token (Contents: Read & write): ")
!apt-get -qq install -y git-lfs >/dev/null 2>&1; git lfs install
```

### Cell 2 — clone the branch
```python
import os
url = f"https://x-access-token:{os.environ['GH_TOKEN']}@github.com/Totti-Grando/Cauterize.git"
!git clone --branch feature/relevance-ce --single-branch {url} /content/Cauterize
%cd /content/Cauterize/relevance_ce
!git config user.email "colab@local"; git config user.name "colab-runner"
```

### Cell 3 — deps (Colab already ships CUDA torch; don't reinstall it)
```python
!pip -q install "transformers>=4.51" "sentence-transformers>=5.5" datasets onnx onnxruntime onnxscript anthropic
import torch; print("torch", torch.__version__, torch.cuda.is_available(), torch.cuda.get_device_name(0))
```

### Cell 4 — synthetic + real HotpotQA
```python
!python generate_synthetic.py --n_questions 12000 --out data/synthetic.jsonl
!python fetch_public.py --sources hotpotqa
!python build_dataset.py
```

### Cell 5 — fine-tune (fp32 on T4; drop --epochs for the full 3-epoch run)
```python
!python train_teacher.py --data data/mix/mix.jsonl --init cross-encoder/ettin-reranker-150m-v1 --out runs/teacher-150m --epochs 1
```

### Cell 6 — score + export int8 ONNX
```python
!python score.py --model runs/teacher-150m --eval data/mix/mix.jsonl --split test
!python export_onnx.py --model runs/teacher-150m --out deploy/model-150m
```

### Cell 6b — Drive backup (safety net; run BEFORE the push)
```python
from google.colab import drive
drive.mount('/content/drive')
!mkdir -p "/content/drive/MyDrive/relevance_ce_model"
!cp -r deploy/model-150m "/content/drive/MyDrive/relevance_ce_model/"
print("model backed up to Drive/relevance_ce_model/")
```

### Cell 7 — push int8 only (stays under the 1 GB free LFS cap)
```python
!cd /content/Cauterize && git add -f relevance_ce/deploy/model-150m/model.int8.onnx relevance_ce/deploy/model-150m/meta.json relevance_ce/deploy/model-150m/report.json relevance_ce/deploy/model-150m/tokenizer
!cd /content/Cauterize && git commit -m "Colab run: trained + exported teacher-150m (synthetic + hotpotqa)"
!cd /content/Cauterize && git push origin HEAD:feature/relevance-ce
```

## Back on your machine
```
git pull && git lfs pull
```
If the push failed but Cell 6b ran, pull the model from `Drive/MyDrive/relevance_ce_model/model-150m`
instead.
