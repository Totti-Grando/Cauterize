"""
Distill the 150M teacher into a small student for the weaker machine.

    python distill_student.py --teacher runs/teacher-150m \
        --data data/synthetic.jsonl data/labeled_real.jsonl \
        --unlabeled data/unlabeled_real.jsonl \
        --init cross-encoder/ettin-reranker-32m-v1 --out runs/student-32m

Loss = alpha * T^2 * KL(teacher || student at temperature T) + (1 - alpha) * CE(hard label).
--unlabeled: real (question, claim) pairs from your pipeline with no label; the teacher's
soft labels are the only target there. This is where most of the student's gain comes from,
so feed it as many real pairs as you have.
"""
from __future__ import annotations

import argparse
import json
import random
import time
from pathlib import Path

import torch
import torch.nn.functional as F

from common import (L2I, build_model, encode_batch, evaluate, fit_temperature, format_pair, load_jsonl,
                    load_model, lr_lambda, predict_logits, save_model, set_seed)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--teacher", required=True)
    ap.add_argument("--data", nargs="+", required=True)
    ap.add_argument("--unlabeled", nargs="*", default=[])
    ap.add_argument("--init", default="cross-encoder/ettin-reranker-32m-v1")
    ap.add_argument("--out", default="runs/student")
    ap.add_argument("--epochs", type=int, default=4)
    ap.add_argument("--batch_size", type=int, default=128)
    ap.add_argument("--lr", type=float, default=8e-5)
    ap.add_argument("--head_lr", type=float, default=3e-4)
    ap.add_argument("--alpha", type=float, default=0.7)
    ap.add_argument("--kd_temp", type=float, default=2.0)
    ap.add_argument("--tag_dropout", type=float, default=0.3)
    ap.add_argument("--tag_noise", type=float, default=0.07)
    ap.add_argument("--max_length", type=int, default=128)
    ap.add_argument("--attn", default=None)
    ap.add_argument("--max_steps", type=int, default=0)
    ap.add_argument("--seed", type=int, default=12)
    args = ap.parse_args()
    set_seed(args.seed)
    rng = random.Random(args.seed)
    device = "cuda" if torch.cuda.is_available() else "cpu"

    train, val, test = [], [], []
    for p in args.data:
        train += load_jsonl(p, "train"); val += load_jsonl(p, "val"); test += load_jsonl(p, "test")
    unl = []
    for p in args.unlabeled:
        unl += [dict(r, label=None, split="train") for r in load_jsonl(p)]
    rows = train + unl
    print(f"labeled {len(train):,}  unlabeled {len(unl):,}  val {len(val):,}  device {device}")

    # 1. teacher soft targets (with tags, raw logits; temperature applied in the loss)
    teacher, ttok, tmeta = load_model(args.teacher, device=device, attn_impl=args.attn)
    t0 = time.time()
    tlogits = predict_logits(teacher, ttok, rows, args.max_length, device=device)
    print(f"teacher logits for {len(rows):,} pairs in {time.time() - t0:.0f}s")
    del teacher
    if device == "cuda":
        torch.cuda.empty_cache()
    for r, l in zip(rows, tlogits):
        r["_t"] = l

    # 2. student
    model, tok, src = build_model(args.init, attn_impl=args.attn)
    print("student init:", src)
    model.to(device).train()
    head = [p for n, p in model.named_parameters() if not n.startswith("encoder.")]
    enc = [p for n, p in model.named_parameters() if n.startswith("encoder.")]
    opt = torch.optim.AdamW([{"params": enc, "lr": args.lr}, {"params": head, "lr": args.head_lr}],
                            weight_decay=0.01)
    spe = (len(rows) + args.batch_size - 1) // args.batch_size
    total = spe * args.epochs if not args.max_steps else args.max_steps
    sched = torch.optim.lr_scheduler.LambdaLR(opt, lr_lambda(int(0.06 * total), total))
    T, best, step = args.kd_temp, -1.0, 0

    for epoch in range(args.epochs):
        rng.shuffle(rows)
        for i in range(0, len(rows), args.batch_size):
            b = rows[i:i + args.batch_size]
            x = encode_batch(tok, [format_pair(r, rng, args.tag_dropout, args.tag_noise) for r in b],
                             args.max_length, device)
            tl = torch.stack([r["_t"] for r in b]).to(device)
            with torch.autocast(device_type="cuda", dtype=torch.bfloat16, enabled=(device == "cuda")):
                sl = model(**x).float()
            kd = F.kl_div(F.log_softmax(sl / T, -1), F.softmax(tl / T, -1), reduction="batchmean") * T * T
            has = [j for j, r in enumerate(b) if r.get("label")]
            ce = torch.tensor(0.0, device=device)
            if has:
                y = torch.tensor([L2I[b[j]["label"]] for j in has], device=device)
                ce = F.cross_entropy(sl[has], y, label_smoothing=0.05)
            loss = args.alpha * kd + (1 - args.alpha) * ce
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step(); sched.step(); opt.zero_grad(set_to_none=True)
            step += 1
            if step % 50 == 0:
                print(f"epoch {epoch} step {step}/{total} kd {kd.item():.4f} ce {ce.item():.4f}")
            if args.max_steps and step >= args.max_steps:
                break
        m = evaluate(predict_logits(model, tok, val, args.max_length, device=device), val)
        key = m["scorecard"]["balanced_accuracy"]
        sc = m["scorecard"]
        print(f"[epoch {epoch}] val missed {sc['missed_rate']:.1%} fooled {sc['fooled_rate']:.1%} "
              f"balanced {sc['balanced_accuracy']:.1%} | macroF1 {m['macro_f1']}")
        if key > best:
            best = key
            save_model(model, tok, args.out, {"init": args.init, "teacher": args.teacher,
                                              "max_length": args.max_length})
        model.train()
        if args.max_steps and step >= args.max_steps:
            break

    model, tok, _ = load_model(args.out, device=device)
    vlog = predict_logits(model, tok, val, args.max_length, device=device)
    Tcal = fit_temperature(vlog, val)
    model.temperature.fill_(Tcal)
    save_model(model, tok, args.out, {"init": args.init, "teacher": args.teacher, "max_length": args.max_length})
    rep_obj = rep = {"temperature": Tcal, "val": evaluate(vlog, val, Tcal)}
    if test:
        rep["test"] = evaluate(predict_logits(model, tok, test, args.max_length, device=device), test, Tcal)
    (Path(args.out) / "report.json").write_text(json.dumps(rep, indent=2))
    from common import format_scorecard
    for k, v in rep_obj.items():
        if k == "temperature":
            print(f"temperature {v:.3f}")
            continue
        print(format_scorecard(v["scorecard"], f"\n{k} scorecard"))
        print("  hygiene:", {kk: vv for kk, vv in v.items() if kk not in ("per_class", "scorecard")})


if __name__ == "__main__":
    main()
