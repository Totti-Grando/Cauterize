"""
Fine-tune the 9-class relevance teacher (default: ettin-reranker-150m on an RTX 5080).

    python train_teacher.py --data data/synthetic.jsonl data/labeled_real.jsonl \
        --init cross-encoder/ettin-reranker-150m-v1 --out runs/teacher-150m

Each --data file is JSONL with: qid, question, q_tags, claim, c_tags, label, split
(train/val/test). Optional per-row `weight` (e.g. 0.3 for weakly labeled public data).
Split by entity or question cluster upstream, never by pair.
"""
from __future__ import annotations

import argparse
import json
import random
import time
from collections import Counter

import torch
import torch.nn.functional as F

from common import (L2I, LABELS, build_model, encode_batch, evaluate, fit_temperature, format_pair,
                    load_jsonl, lr_lambda, predict_logits, save_model, set_seed)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", nargs="+", required=True)
    ap.add_argument("--init", default="cross-encoder/ettin-reranker-150m-v1")
    ap.add_argument("--out", default="runs/teacher")
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--batch_size", type=int, default=64)
    ap.add_argument("--lr", type=float, default=2e-5)
    ap.add_argument("--head_lr", type=float, default=1e-4)
    ap.add_argument("--warmup", type=float, default=0.06)
    ap.add_argument("--weight_decay", type=float, default=0.01)
    ap.add_argument("--label_smoothing", type=float, default=0.1)
    ap.add_argument("--class_weights", action="store_true", help="inverse-sqrt-frequency class weights")
    ap.add_argument("--tag_dropout", type=float, default=0.3)
    ap.add_argument("--tag_noise", type=float, default=0.07)
    ap.add_argument("--max_length", type=int, default=128)
    ap.add_argument("--attn", default=None, help="sdpa | flash_attention_2 (leave unset if unsure)")
    ap.add_argument("--eval_every", type=int, default=0, help="steps; 0 = once per epoch")
    ap.add_argument("--max_steps", type=int, default=0, help="debug: stop after N steps")
    ap.add_argument("--seed", type=int, default=12)
    args = ap.parse_args()
    set_seed(args.seed)
    rng = random.Random(args.seed)
    device = "cuda" if torch.cuda.is_available() else "cpu"

    train, val, test = [], [], []
    for p in args.data:
        train += load_jsonl(p, "train"); val += load_jsonl(p, "val"); test += load_jsonl(p, "test")
    print(f"train {len(train):,}  val {len(val):,}  test {len(test):,}  device {device}")
    print("train labels:", dict(Counter(r["label"] for r in train)))

    model, tok, src = build_model(args.init, attn_impl=args.attn)
    print("init:", src)
    model.to(device)

    cw = None
    if args.class_weights:
        cnt = Counter(r["label"] for r in train)
        cw = torch.tensor([1.0 / max(1, cnt.get(l, 1)) ** 0.5 for l in LABELS])
        cw = (cw / cw.mean()).to(device)

    head_params = [p for n, p in model.named_parameters() if not n.startswith("encoder.")]
    enc_params = [p for n, p in model.named_parameters() if n.startswith("encoder.")]
    opt = torch.optim.AdamW([{"params": enc_params, "lr": args.lr},
                             {"params": head_params, "lr": args.head_lr}], weight_decay=args.weight_decay)
    steps_per_epoch = (len(train) + args.batch_size - 1) // args.batch_size
    total = steps_per_epoch * args.epochs if not args.max_steps else args.max_steps
    sched = torch.optim.lr_scheduler.LambdaLR(opt, lr_lambda(int(args.warmup * total), total))

    best, step, t0 = -1.0, 0, time.time()

    def run_eval(tag):
        nonlocal best
        logits = predict_logits(model, tok, val, args.max_length, device=device)
        m = evaluate(logits, val)
        key = m["scorecard"]["balanced_accuracy"]
        sc = m["scorecard"]
        print(f"[{tag}] val missed {sc['missed_rate']:.1%} fooled {sc['fooled_rate']:.1%} "
              f"balanced {sc['balanced_accuracy']:.1%} | macroF1 {m['macro_f1']} ECE {m['ece']}  ({time.time() - t0:.0f}s)")
        if key > best:
            best = key
            save_model(model, tok, args.out, {"init": args.init, "max_length": args.max_length})
            print(f"  saved best -> {args.out}")
        model.train()

    model.train()
    for epoch in range(args.epochs):
        rng.shuffle(train)
        for i in range(0, len(train), args.batch_size):
            batch = train[i:i + args.batch_size]
            pairs = [format_pair(r, rng, args.tag_dropout, args.tag_noise) for r in batch]
            enc = encode_batch(tok, pairs, args.max_length, device)
            y = torch.tensor([L2I[r["label"]] for r in batch], device=device)
            w = torch.tensor([float(r.get("weight", 1.0)) for r in batch], device=device)
            with torch.autocast(device_type="cuda", dtype=torch.bfloat16, enabled=(device == "cuda")):
                logits = model(**enc)
            loss = F.cross_entropy(logits.float(), y, weight=cw, label_smoothing=args.label_smoothing,
                                   reduction="none")
            loss = (loss * w).sum() / w.sum()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step(); sched.step(); opt.zero_grad(set_to_none=True)
            step += 1
            if step % 50 == 0:
                print(f"epoch {epoch} step {step}/{total} loss {loss.item():.4f}")
            if args.eval_every and step % args.eval_every == 0:
                run_eval(f"step {step}")
            if args.max_steps and step >= args.max_steps:
                break
        if not args.eval_every:
            run_eval(f"epoch {epoch}")
        if args.max_steps and step >= args.max_steps:
            break

    # reload best, calibrate on val, report test
    from common import load_model
    model, tok, meta = load_model(args.out, device=device, attn_impl=args.attn)
    vlog = predict_logits(model, tok, val, args.max_length, device=device)
    T = fit_temperature(vlog, val)
    model.temperature.fill_(T)
    save_model(model, tok, args.out, {"init": args.init, "max_length": args.max_length})
    rep_obj = report = {"temperature": T, "val": evaluate(vlog, val, T)}
    if test:
        tlog = predict_logits(model, tok, test, args.max_length, device=device)
        report["test"] = evaluate(tlog, test, T)
        report["test_no_tags"] = evaluate(predict_logits(model, tok, test, args.max_length, device=device,
                                                          use_tags=False), test, T)
    (__import__("pathlib").Path(args.out) / "report.json").write_text(json.dumps(report, indent=2))
    from common import format_scorecard
    for k, v in rep_obj.items():
        if k == "temperature":
            print(f"temperature {v:.3f}")
            continue
        print(format_scorecard(v["scorecard"], f"\n{k} scorecard"))
        print("  hygiene:", {kk: vv for kk, vv in v.items() if kk not in ("per_class", "scorecard")})


if __name__ == "__main__":
    main()
