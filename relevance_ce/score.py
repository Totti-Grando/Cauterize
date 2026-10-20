"""
Score claims against a question: top class = answer, its utility tier = relevance, symbolic gates.

Library use:
    from score import Scorer
    s = Scorer("deploy/student-32m")             # ONNX dir (int8 by default) or a torch run dir
    results = s.score(question, q_tags, [(claim, c_tags), ...])

CLI:
    python score.py --model deploy/student-32m --demo            # 40-claim demo + timing
    python score.py --model deploy/student-32m --bench 200       # latency over 200 calls
    python score.py --model deploy/student-32m --eval data/synthetic.jsonl --split test
    python score.py --model deploy/student-32m --check_against runs/student-32m   # int8 vs fp32 drift
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import time
from pathlib import Path

import numpy as np

TIME_RE = re.compile(r"\[TIME\]\s+(\S+)")


def _softmax(x):
    x = x - x.max(-1, keepdims=True)
    e = np.exp(x)
    return e / e.sum(-1, keepdims=True)


def _period_bounds(tag: str):
    """'2026Q2', '2026H1', 'FY2025', 'FY2021-FY2024', '2024-03' -> (start, end) in years; else None."""
    m = re.fullmatch(r"(\d{4})Q([1-4])", tag)
    if m:
        y, q = int(m[1]), int(m[2]); return (y + (q - 1) / 4, y + q / 4)
    m = re.fullmatch(r"FY(\d{4})-FY(\d{4})", tag)
    if m:
        return (int(m[1]), int(m[2]) + 1)
    m = re.fullmatch(r"(\d{4})H([12])", tag)
    if m:
        y, h = int(m[1]), int(m[2]); return (y + (h - 1) / 2, y + h / 2)
    m = re.fullmatch(r"FY(\d{4})", tag)
    if m:
        y = int(m[1]); return (y, y + 1)
    m = re.fullmatch(r"(\d{4})-(\d{2})", tag)
    if m:
        y, mo = int(m[1]), int(m[2]); return (y + (mo - 1) / 12, y + mo / 12)
    return None


def apply_gates(label: str, q_tags: str, c_tags: str, utility: dict, use_gates: bool = True):
    """Override the model's label where a mechanical tag check is decisive.
    Returns (label, gate_name|None). Only ever moves a label DOWN the utility ladder."""
    if not use_gates:
        return label, None
    if "[ENT] UNRESOLVED" in c_tags and utility[label] > utility["UNRESOLVED"]:
        return "UNRESOLVED", "unresolved_entity"
    qt, ct = TIME_RE.search(q_tags or ""), TIME_RE.search(c_tags or "")
    if qt and ct and qt[1] != "NONE" and ct[1] != "NONE":
        qb, cb = _period_bounds(qt[1]), _period_bounds(ct[1])
        no_overlap = qb and cb and (cb[1] <= qb[0] or cb[0] >= qb[1])
        if no_overlap and utility[label] > utility["WRONG_TIME"]:
            return "WRONG_TIME", "time_mismatch"
    return label, None


class Scorer:
    def __init__(self, model_dir, int8=True, threads=None, max_length=None):
        d = Path(model_dir)
        self.meta = json.loads((d / "meta.json").read_text())
        self.labels = self.meta["labels"]
        self.u = np.array([self.meta["utility"][l] for l in self.labels], dtype=np.float32)
        self.T = float(self.meta.get("temperature", 1.0))
        self.max_length = max_length or int(self.meta.get("max_length", 128))
        from transformers import AutoTokenizer
        onnx = d / ("model.int8.onnx" if int8 and (d / "model.int8.onnx").exists() else "model.onnx")
        if onnx.exists():
            import onnxruntime as ort
            so = ort.SessionOptions()
            if threads:
                so.intra_op_num_threads = threads
            self.sess = ort.InferenceSession(str(onnx), so, providers=["CPUExecutionProvider"])
            self.tok = AutoTokenizer.from_pretrained(d / "tokenizer")
            self.backend = f"onnx:{onnx.name}"
        else:
            import torch
            from common import load_model
            self.torch = torch
            self.model, self.tok, _ = load_model(d, device="cpu")
            self.sess = None
            self.backend = "torch"

    def logits(self, queries, docs):
        enc = self.tok(queries, docs, padding=True, truncation="longest_first", max_length=self.max_length,
                       return_tensors="np")
        if self.sess is not None:
            return self.sess.run(["logits"], {"input_ids": enc["input_ids"].astype(np.int64),
                                              "attention_mask": enc["attention_mask"].astype(np.int64)})[0]
        with self.torch.no_grad():
            t = {k: self.torch.from_numpy(v) for k, v in enc.items() if k in ("input_ids", "attention_mask")}
            return self.model(**t).float().numpy()

    def score(self, question, q_tags, claims, use_gates=True):
        """Per claim: the most likely class is the answer; relevance is that class's utility.
        `confidence` is the model's probability for its own top class; `probs` shows all nine."""
        q = f"[Q] {question} {q_tags or ''}".strip()
        docs = [f"[C] {c} {t or ''}".strip() for c, t in claims]
        probs = _softmax(self.logits([q] * len(docs), docs) / self.T)
        util = self.meta["utility"]
        out = []
        for (c, t), p in zip(claims, probs):
            top = int(p.argmax())
            model_label = self.labels[top]
            label, gate = apply_gates(model_label, q_tags or "", t or "", util, use_gates)
            conf = float(p[top])
            out.append({"claim": c, "label": label, "relevance": util[label],
                        "confidence": round(conf, 4), "uncertain": conf < 0.5,
                        "model_label": model_label, "gate": gate,
                        "probs": {l: round(float(x), 4) for l, x in zip(self.labels, p)}})
        # rank by tier, then by confidence within the tier
        return out

    @staticmethod
    def ranked(results):
        return sorted(results, key=lambda r: (-r["relevance"], -r["confidence"]))


DEMO_Q = ("What were Northwind's net flows in Q2 2026?", "[ENT] Northwind Asset Management:ORG [TIME] 2026Q2 [ATTR] net_flows")
DEMO_CLAIMS = [
    ("Northwind took in $1.2B of net flows in Q2 2026.", "[ENT] Northwind Asset Management:ORG=MATCH [TIME] 2026Q2 [ATTR] net_flows"),
    ("Northwind's ETF lineup gathered $700M in Q2 2026.", "[ENT] Northwind Asset Management:ORG=MATCH [TIME] 2026Q2 [ATTR] net_flows"),
    ("Northwind gathered $400M in net new money in Q2 2024.", "[ENT] Northwind Asset Management:ORG=MATCH [TIME] 2024Q2 [ATTR] net_flows"),
    ("Northwind launched 6 new funds in Q2 2026.", "[ENT] Northwind Asset Management:ORG=MATCH [TIME] 2026Q2 [ATTR] fund_launches"),
    ("Ashgrove took in $900M of net flows in Q2 2026.", "[ENT] Ashgrove Investments:ORG=ADJACENT [TIME] 2026Q2 [ATTR] net_flows"),
    ("The firm gathered $1.2B in net new money this spring.", "[ENT] UNRESOLVED [TIME] NONE [ATTR] net_flows"),
    ("Canadian fund industry net flows reached $14.0B in Q2 2026.", "[ENT] NONE [TIME] 2026Q2 [ATTR] net_flows"),
    ("Maplecrest Foods opened three new plants in 2025.", "[ENT] NONE [TIME] NONE"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--fp32", action="store_true", help="use model.onnx instead of model.int8.onnx")
    ap.add_argument("--threads", type=int, default=None)
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--bench", type=int, default=0)
    ap.add_argument("--n_claims", type=int, default=40)
    ap.add_argument("--eval", default=None)
    ap.add_argument("--split", default="test")
    ap.add_argument("--check_against", default=None, help="torch run dir to compare probabilities with")
    args = ap.parse_args()
    s = Scorer(args.model, int8=not args.fp32, threads=args.threads)
    print("backend:", s.backend)

    claims40 = (DEMO_CLAIMS * ((args.n_claims // len(DEMO_CLAIMS)) + 1))[:args.n_claims]
    if args.demo:
        t = time.perf_counter(); res = s.score(*DEMO_Q, DEMO_CLAIMS); dt = time.perf_counter() - t
        for r in Scorer.ranked(res):
            flag = "?" if r["uncertain"] else " "
            print(f"{r['relevance']:.2f}  {r['label']:15s} {r['confidence']:.2f}{flag} {r['gate'] or '':18s} {r['claim']}")
        print(f"{len(DEMO_CLAIMS)} claims in {dt * 1000:.0f} ms (includes warm-up)")
    if args.bench:
        s.score(*DEMO_Q, claims40)  # warm-up
        ts = []
        for _ in range(args.bench):
            t = time.perf_counter(); s.score(*DEMO_Q, claims40); ts.append(time.perf_counter() - t)
        ts.sort()
        print(f"{args.n_claims} claims/call over {args.bench} calls: median {statistics.median(ts) * 1000:.1f} ms, "
              f"p95 {ts[int(0.95 * len(ts)) - 1] * 1000:.1f} ms")
    if args.eval:
        import torch
        from common import LABELS, RELEVANT, evaluate, format_scorecard, load_jsonl, scorecard
        rows = load_jsonl(args.eval, args.split)
        logits = []
        for i in range(0, len(rows), 256):
            ch = rows[i:i + 256]
            logits.append(s.logits([f"[Q] {r['question']} {r.get('q_tags', '')}".strip() for r in ch],
                                   [f"[C] {r['claim']} {r.get('c_tags', '')}".strip() for r in ch]))
        logits = np.concatenate(logits)
        m = evaluate(torch.from_numpy(logits), rows, s.T)
        model_labels = [LABELS[i] for i in logits.argmax(-1)]
        gated = [apply_gates(l, r.get("q_tags", ""), r.get("c_tags", ""), s.meta["utility"])[0]
                 for l, r in zip(model_labels, rows)]
        print(format_scorecard(m["scorecard"], "Scorecard: model only"))
        print()
        print(format_scorecard(scorecard(gated, rows), "Scorecard: model + gates (what serving returns)"))
        gate_misses = sum(r["label"] in RELEVANT and ml in RELEVANT and gl not in RELEVANT
                          for r, ml, gl in zip(rows, model_labels, gated))
        gate_saves = sum(r["label"] not in RELEVANT and ml in RELEVANT and gl not in RELEVANT
                         for r, ml, gl in zip(rows, model_labels, gated))
        print(f"\n  gates: stopped {gate_saves:,} fooled calls, caused {gate_misses:,} misses "
              f"(a caused miss means a tag was wrong: check the extractor)")
        print("\n  hygiene:", json.dumps({k: v for k, v in m.items() if k not in ("per_class", "scorecard")}))
    if args.check_against:
        ref = Scorer(args.check_against)
        a = s.score(*DEMO_Q, DEMO_CLAIMS, use_gates=False)
        b = ref.score(*DEMO_Q, DEMO_CLAIMS, use_gates=False)
        diffs = [max(abs(x["probs"][l] - y["probs"][l]) for l in x["probs"]) for x, y in zip(a, b)]
        agree = sum(x["label"] == y["label"] for x, y in zip(a, b))
        print(f"max |probability diff| {max(diffs):.4f}, label agreement {agree}/{len(a)} ({s.backend} vs {ref.backend})")


if __name__ == "__main__":
    main()
