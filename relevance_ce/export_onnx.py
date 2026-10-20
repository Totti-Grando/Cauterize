"""
Export a trained model to ONNX (fp32) and dynamically quantized int8 for CPU serving.

    python export_onnx.py --model runs/student-32m --out deploy/student-32m

Writes model.onnx, model.int8.onnx, the tokenizer, and meta.json (labels, utilities, temperature).
Then check int8 against fp32 with:  python score.py --model deploy/student-32m --check_against runs/student-32m
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import torch

from common import load_model


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--opset", type=int, default=17)
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    model, tok, meta = load_model(args.model, device="cpu", attn_impl="eager")
    model.float().eval()
    dummy = tok(["[Q] What were Northwind's net flows in Q2 2026?"], ["[C] Northwind took in $1.2B."],
                return_tensors="pt", padding=True)
    inputs = (dummy["input_ids"], dummy["attention_mask"])

    class Wrap(torch.nn.Module):
        def __init__(self, m):
            super().__init__(); self.m = m

        def forward(self, input_ids, attention_mask):
            return self.m(input_ids=input_ids, attention_mask=attention_mask)

    fp32 = out / "model.onnx"
    export_kw = dict(input_names=["input_ids", "attention_mask"], output_names=["logits"],
                     dynamic_axes={"input_ids": {0: "batch", 1: "seq"}, "attention_mask": {0: "batch", 1: "seq"},
                                   "logits": {0: "batch"}}, opset_version=args.opset)
    try:
        torch.onnx.export(Wrap(model), inputs, str(fp32), dynamo=False, **export_kw)
    except TypeError:  # older torch without the dynamo flag
        torch.onnx.export(Wrap(model), inputs, str(fp32), **export_kw)
    print("wrote", fp32)

    from onnxruntime.quantization import QuantType, quantize_dynamic
    int8 = out / "model.int8.onnx"
    quantize_dynamic(str(fp32), str(int8), weight_type=QuantType.QInt8)
    print("wrote", int8)

    tok.save_pretrained(out / "tokenizer")
    (out / "meta.json").write_text(json.dumps(meta, indent=2))
    for f in ("report.json",):
        if (Path(args.model) / f).exists():
            shutil.copy(Path(args.model) / f, out / f)
    print("sizes (MB):", {p.name: round(p.stat().st_size / 1e6, 1) for p in out.glob("*.onnx")})


if __name__ == "__main__":
    main()
