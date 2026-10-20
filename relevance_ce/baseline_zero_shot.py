"""
Zero-shot baseline: score the same eval rows with an off-the-shelf reranker (no fine-tuning)
and report NDCG@5 and minimal-pair accuracy on graded utilities, for the "Baseline" gate.

    python baseline_zero_shot.py --data data/labeled_real.jsonl --split test \
        --reranker cross-encoder/ettin-reranker-150m-v1

Tags are not passed to the baseline (it was never trained on them). Compare against the
`ndcg@5` and `pair_accuracy` in your fine-tuned model's report.json.
"""
from __future__ import annotations

import argparse
import json

from common import load_jsonl, ndcg_at_k


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--split", default="test")
    ap.add_argument("--reranker", default="cross-encoder/ettin-reranker-150m-v1")
    args = ap.parse_args()
    from sentence_transformers import CrossEncoder
    rows = load_jsonl(args.data, args.split)
    ce = CrossEncoder(args.reranker)
    scores = ce.predict([(r["question"], r["claim"]) for r in rows], batch_size=256, show_progress_bar=True)
    scores = [float(s) for s in scores]
    groups = {}
    for i, r in enumerate(rows):
        groups.setdefault(r["qid"], []).append(i)
    wins = total = 0
    for idx in groups.values():
        d = [i for i in idx if rows[i]["label"] == "DIRECT"]
        o = [i for i in idx if rows[i]["label"] != "DIRECT"]
        for a in d:
            for b in o:
                total += 1
                wins += int(scores[a] > scores[b])
    print(json.dumps({"reranker": args.reranker, "rows": len(rows), "ndcg@5": round(ndcg_at_k(scores, rows, 5), 4),
                      "pair_accuracy": round(wins / total, 4) if total else None}, indent=2))


if __name__ == "__main__":
    main()
