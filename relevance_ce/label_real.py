"""
Label your real (question, claim) pairs with the 9-class rubric using Claude, in two passes.

    pip install anthropic
    export ANTHROPIC_API_KEY=...
    # 1. training labels: full first pass, independent second pass on 10% for agreement
    python label_real.py --in data/real_pairs.jsonl --out data/labeled_real.jsonl --second_pass 0.10
    # 2. hold-out set: both passes on everything, disagreements exported for you to adjudicate
    python label_real.py --in data/holdout_pairs.jsonl --out data/holdout.jsonl --holdout
    #    ...edit data/holdout.disagreements.csv (fill the `final` column), then:
    python label_real.py --apply_adjudication data/holdout.disagreements.csv --out data/holdout.jsonl

Input rows (one per pair; grouped by qid so the labeler sees each question's full claim set):
    {"qid": "...", "question": "...", "q_tags": "...", "claim": "...", "c_tags": "...",
     "split_key": "<optional: your primary entity id; default = first [ENT] name in q_tags>"}

Output rows match the training format, plus label_confidence, label_reason, pass2_label, source.
Weights: 1.0 when both passes agree or a human adjudicated; 0.5 for single-pass labels with
confidence < 0.7; rows below 0.4 confidence are dropped. Prints per-class agreement between passes.
The rubric text is read from label_rubric_prompt.md (one source of truth).
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import re
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

LABELS = ["IRRELEVANT", "UNRESOLVED", "ECOSYSTEM", "WRONG_RELATION", "WRONG_INTENT",
          "WRONG_TIME", "DIRECT", "PARTIAL", "CONTEXT"]
UTIL = {"IRRELEVANT": 0.0, "ECOSYSTEM": 0.1, "WRONG_RELATION": 0.15, "WRONG_INTENT": 0.2,
        "UNRESOLVED": 0.25, "WRONG_TIME": 0.3, "CONTEXT": 0.4, "PARTIAL": 0.7, "DIRECT": 1.0}


def rubric_system_prompt(path="label_rubric_prompt.md"):
    text = Path(path).read_text(encoding="utf-8")
    m = re.search(r"## System prompt\s*\n(.*?)\n## User message template", text, re.S)
    if not m:
        raise SystemExit(f"could not find the system prompt section in {path}")
    return m.group(1).strip()


def user_message(question, q_tags, claims):
    lines = [f"QUESTION: {question}", f"QUESTION TAGS: {q_tags or 'NONE'}", "", "CLAIMS:"]
    for i, (c, t) in enumerate(claims, 1):
        lines.append(f"{i}. {c}  || {t or 'NONE'}")
    lines += ["", "Return JSON only:",
              '[{"id": 1, "label": "<ONE OF THE 9 LABELS>", "confidence": <0-1>, "reason": "<= 12 words"}, ...]',
              f"Labels: {', '.join(LABELS)}. Return exactly {len(claims)} items."]
    return "\n".join(lines)


def parse_reply(text, n):
    m = re.search(r"\[.*\]", text, re.S)
    if not m:
        raise ValueError("no JSON array in reply")
    items = json.loads(m.group(0))
    out = {}
    for it in items:
        lab = str(it.get("label", "")).strip().upper()
        if lab in LABELS and isinstance(it.get("id"), int) and 1 <= it["id"] <= n:
            out[it["id"]] = (lab, float(it.get("confidence", 0.5)), str(it.get("reason", ""))[:200])
    if len(out) < n:
        raise ValueError(f"reply covered {len(out)}/{n} claims")
    return out


class Labeler:
    def __init__(self, model, system, max_tokens=4000, client=None):
        if client is None:
            import anthropic
            client = anthropic.Anthropic()
        self.client, self.model, self.system, self.max_tokens = client, model, system, max_tokens

    def label(self, question, q_tags, claims, tries=4):
        msg = user_message(question, q_tags, claims)
        for k in range(tries):
            try:
                r = self.client.messages.create(model=self.model, max_tokens=self.max_tokens, system=self.system,
                                                messages=[{"role": "user", "content": msg}])
                text = "".join(getattr(b, "text", "") for b in r.content)
                return parse_reply(text, len(claims))
            except Exception as e:  # rate limits, malformed JSON: back off and retry
                if k == tries - 1:
                    raise
                time.sleep(2 ** k + random.random())


def split_for(key):
    h = int(hashlib.md5(key.encode()).hexdigest(), 16) % 100
    return "train" if h < 80 else ("val" if h < 90 else "test")


def split_key(row):
    if row.get("split_key"):
        return row["split_key"]
    m = re.search(r"\[ENT\]\s+([^:|\[]+)", row.get("q_tags", "") or "")
    return m.group(1).strip() if m else row["qid"]


def run_pass(labeler, groups, workers, shuffle_seed=None):
    """Returns {(qid, claim_index): (label, conf, reason)}. shuffle_seed reorders claims (pass 2)."""
    results = {}

    def job(qid, rows):
        order = list(range(len(rows)))
        if shuffle_seed is not None:
            random.Random(f"{shuffle_seed}-{qid}").shuffle(order)
        claims = [(rows[i]["claim"], rows[i].get("c_tags", "")) for i in order]
        out = labeler.label(rows[0]["question"], rows[0].get("q_tags", ""), claims)
        return qid, {order[k - 1]: v for k, v in out.items()}

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(job, q, rs) for q, rs in groups.items()]
        for i, f in enumerate(as_completed(futs), 1):
            try:
                qid, res = f.result()
                for idx, v in res.items():
                    results[(qid, idx)] = v
            except Exception as e:
                print(f"  question failed after retries: {type(e).__name__}: {str(e)[:120]}")
            if i % 25 == 0:
                print(f"  {i}/{len(futs)} questions")
    return results


def agreement_report(p1, p2):
    both = [(p1[k][0], p2[k][0]) for k in p2 if k in p1]
    if not both:
        return None
    by = defaultdict(lambda: [0, 0])
    for a, b in both:
        by[a][1] += 1
        by[a][0] += int(a == b)
    overall = sum(a == b for a, b in both) / len(both)
    print(f"\nInter-pass agreement: {overall:.1%} on {len(both):,} pairs (target >= 85%)")
    for lab in LABELS:
        if by[lab][1]:
            ok, n = by[lab]
            flag = "  <- tighten rubric or merge" if ok / n < 0.7 and n >= 20 else ""
            print(f"  {lab:15s} {ok / n:6.1%}  (n={n}){flag}")
    rel = {"DIRECT", "PARTIAL"}
    rel_agree = sum((a in rel) == (b in rel) for a, b in both) / len(both)
    print(f"  relevant / not-relevant agreement: {rel_agree:.1%}")
    return overall


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp")
    ap.add_argument("--out", required=True)
    ap.add_argument("--model", default="claude-sonnet-5-5")
    ap.add_argument("--model2", default=None, help="model for pass 2 (default: same model, claims reordered)")
    ap.add_argument("--second_pass", type=float, default=0.10, help="share of questions given a second pass")
    ap.add_argument("--holdout", action="store_true", help="second pass on everything; split forced to test")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--max_questions", type=int, default=0)
    ap.add_argument("--rubric", default="label_rubric_prompt.md")
    ap.add_argument("--apply_adjudication", default=None)
    args = ap.parse_args()
    out = Path(args.out)

    if args.apply_adjudication:
        rows = [json.loads(l) for l in out.open(encoding="utf-8")]
        fixes = {}
        with open(args.apply_adjudication, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                fin = (r.get("final") or "").strip().upper()
                if fin in LABELS:
                    fixes[(r["qid"], r["claim"])] = fin
        n = 0
        for r in rows:
            k = (r["qid"], r["claim"])
            if k in fixes:
                r.update(label=fixes[k], utility=UTIL[fixes[k]], weight=1.0, source=r.get("source", "") + "+human")
                n += 1
        with out.open("w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"applied {n} adjudicated labels -> {out}")
        return

    pairs = [json.loads(l) for l in open(args.inp, encoding="utf-8")]
    groups = defaultdict(list)
    for r in pairs:
        groups[r["qid"]].append(r)
    if args.max_questions:
        groups = dict(list(groups.items())[:args.max_questions])
    print(f"{sum(len(v) for v in groups.values()):,} pairs in {len(groups):,} questions")

    system = rubric_system_prompt(args.rubric)
    p1 = run_pass(Labeler(args.model, system), groups, args.workers)
    share = 1.0 if args.holdout else args.second_pass
    sample = {q: rs for q, rs in groups.items() if random.Random(q).random() < share}
    p2 = run_pass(Labeler(args.model2 or args.model, system), sample, args.workers, shuffle_seed=1) if sample else {}
    agreement_report(p1, p2)

    rows_out, disagreements, dropped = [], [], 0
    for qid, rs in groups.items():
        for i, r in enumerate(rs):
            if (qid, i) not in p1:
                continue
            lab, conf, reason = p1[(qid, i)]
            lab2 = p2.get((qid, i), (None,))[0]
            if lab2 is not None and lab2 != lab:
                disagreements.append({"qid": qid, "question": r["question"], "claim": r["claim"],
                                      "pass1": lab, "pass2": lab2, "final": ""})
                weight = 0.0 if args.holdout else 0.5          # hold-out rows wait for adjudication
            elif lab2 is not None:
                weight = 1.0
            else:
                if conf < 0.4:
                    dropped += 1
                    continue
                weight = 1.0 if conf >= 0.7 else 0.5
            rows_out.append({"qid": qid, "question": r["question"], "q_tags": r.get("q_tags", ""),
                             "claim": r["claim"], "c_tags": r.get("c_tags", ""), "label": lab, "utility": UTIL[lab],
                             "split": "test" if args.holdout else split_for(split_key(r)), "weight": weight,
                             "label_confidence": conf, "label_reason": reason, "pass2_label": lab2,
                             "source": "llm_holdout" if args.holdout else "llm_v1"})
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for r in rows_out:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"\nwrote {len(rows_out):,} rows -> {out}  (dropped {dropped} low-confidence)")
    print("labels:", dict(Counter(r["label"] for r in rows_out)))
    if disagreements:
        dpath = out.with_suffix(".disagreements.csv")
        with dpath.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(disagreements[0]))
            w.writeheader(); w.writerows(disagreements)
        print(f"{len(disagreements)} disagreements -> {dpath}  (fill `final`, then --apply_adjudication)")


if __name__ == "__main__":
    main()
