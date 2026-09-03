#!/usr/bin/env python3
"""Fetch the local DeBERTa NLI weights for the claim-graph grounding pipeline.

The weights (~360 MB) are too large for git and ``models/`` is gitignored, so they ship as a
GitHub *Release asset* on the public ``Totti-Grando/Cauterize`` repo. This script downloads that
asset and unpacks it into ``Agentic_Eval/models/deberta-mnli-fever-anli/`` — the layout the local
loader (:mod:`aah.api.local_nli`) expects.

Why a plain-``urllib`` download (no HuggingFace, no ``gh``): the target machine is firewalled off
from HuggingFace and may not have the GitHub CLI. The repo is public, so the asset URL needs no
auth. Everything here is stdlib.

Usage (from the ``Agentic_Eval`` directory)::

    python scripts/fetch_model.py            # download + verify + unzip (skips if already present)
    python scripts/fetch_model.py --force    # re-download even if the model is already there
    python scripts/fetch_model.py --keep-zip # don't delete the .zip after extracting

Then point the harness at it (HuggingFace-free)::

    # bash
    export AAH_NLI_MODEL="$(pwd)/models/deberta-mnli-fever-anli"
    export HF_HUB_OFFLINE=1
    # on the Intel-GPU box also: export AAH_NLI_DEVICE=xpu

    # PowerShell
    $env:AAH_NLI_MODEL = "$PWD/models/deberta-mnli-fever-anli"
    $env:HF_HUB_OFFLINE = "1"
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import zipfile
from pathlib import Path
from urllib.request import Request, urlopen

# --- release coordinates (keep in sync with the actual GitHub Release) --------------
REPO = "Totti-Grando/Cauterize"
TAG = "nli-model-v1"
ASSET = "deberta-mnli-fever-anli.zip"
URL = f"https://github.com/{REPO}/releases/download/{TAG}/{ASSET}"

# integrity: sha256 + size of the published zip (printed by the release step)
EXPECT_SHA256 = "7cb2554497a461ee171e50589362a6b624d96c33c5984fb55196bd3ef508831c"
EXPECT_SIZE = 341816453

# the four files the local loader needs, unpacked flat into the model dir
MODEL_FILES = ("config.json", "model.safetensors", "tokenizer.json", "tokenizer_config.json")

_HERE = Path(__file__).resolve().parent
MODELS_DIR = _HERE.parent / "models"
MODEL_DIR = MODELS_DIR / "deberta-mnli-fever-anli"


def _fmt(n: int) -> str:
    mb = n / 1024 / 1024
    return f"{mb/1024:.2f} GB" if mb >= 1024 else f"{mb:.1f} MB"


def _already_present() -> bool:
    return MODEL_DIR.is_dir() and all((MODEL_DIR / f).is_file() and (MODEL_DIR / f).stat().st_size > 0
                                      for f in MODEL_FILES)


def _download(dest: Path) -> None:
    print(f"-> downloading {ASSET} ({_fmt(EXPECT_SIZE)}) from {URL}")
    req = Request(URL, headers={"User-Agent": "aah-fetch-model/1.0", "Accept": "application/octet-stream"})
    with urlopen(req) as resp:  # noqa: S310 - fixed, trusted https URL
        total = int(resp.headers.get("Content-Length") or EXPECT_SIZE)
        done = 0
        step = max(1, total // 50)
        next_mark = step
        with open(dest, "wb") as f:
            while True:
                chunk = resp.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                if done >= next_mark:
                    pct = done * 100 // total
                    sys.stdout.write(f"\r  {pct:3d}%  {_fmt(done)} / {_fmt(total)}")
                    sys.stdout.flush()
                    next_mark += step
    print("\r  100%  download complete" + " " * 20)


def _verify(path: Path) -> None:
    size = path.stat().st_size
    if EXPECT_SIZE and size != EXPECT_SIZE:
        raise SystemExit(f"size mismatch: got {size}, expected {EXPECT_SIZE} — download corrupt/incomplete")
    print("-> verifying sha256 ...")
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    got = h.hexdigest()
    if EXPECT_SHA256 and got != EXPECT_SHA256:
        raise SystemExit(f"sha256 mismatch:\n  got      {got}\n  expected {EXPECT_SHA256}")
    print(f"  ok  {got}")


def _extract(zip_path: Path) -> None:
    print(f"-> extracting into {MODEL_DIR}")
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(MODEL_DIR)
    missing = [f for f in MODEL_FILES if not (MODEL_DIR / f).is_file()]
    if missing:
        raise SystemExit(f"extract incomplete — missing: {', '.join(missing)}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Download the DeBERTa NLI weights for claim-graph grounding.")
    ap.add_argument("--force", action="store_true", help="re-download even if the model is already present")
    ap.add_argument("--keep-zip", action="store_true", help="keep the downloaded .zip after extracting")
    args = ap.parse_args()

    if _already_present() and not args.force:
        print(f"[ok] model already present at {MODEL_DIR} — nothing to do (use --force to re-download)")
        return 0

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = MODELS_DIR / ASSET
    if not (zip_path.is_file() and zip_path.stat().st_size == EXPECT_SIZE) or args.force:
        _download(zip_path)
    else:
        print(f"-> reusing existing {zip_path.name}")
    _verify(zip_path)
    _extract(zip_path)
    if not args.keep_zip:
        zip_path.unlink(missing_ok=True)
        print("-> removed the .zip (pass --keep-zip to keep it)")

    print(f"\n[ok] done. model ready at {MODEL_DIR}")
    print("  set  AAH_NLI_MODEL=<that path>  and  HF_HUB_OFFLINE=1  to use it offline.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
