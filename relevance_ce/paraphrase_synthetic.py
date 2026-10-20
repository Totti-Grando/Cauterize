"""
Paraphrase synthetic questions and claims with Claude so the model learns relations, not templates.

    pip install anthropic && export ANTHROPIC_API_KEY=...
    python paraphrase_synthetic.py --in data/synthetic.jsonl --out data/synthetic_para.jsonl \
        --max_questions 3000 --workers 4

Each question is sent with its claims; the model rewrites the wording only. Every rewrite is then
checked mechanically: all numbers, years, quarter markers, tickers and proper names in the original
must survive, and relation direction is protected by requiring the same entity names in the same
order. A rewrite that fails any check is discarded and the original kept, so labels stay valid.
Paraphrased rows carry source=synthetic_v2_para; tags are copied unchanged.
"""
from __future__ import annotations

import argparse
import json
import random
import re
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

SYSTEM = """You rewrite short financial sentences so they say exactly the same thing in different words.
Rules:
- Keep every number, currency amount, percentage, date, quarter, year and ticker exactly as written.
- Keep every company, person and regulator name exactly as written, in the same order.
- Keep who did what to whom: never swap the subject and object of an action.
- Keep vague references vague ("the firm", "it", "this spring" stay unspecific).
- Keep each sentence short: 5 to 14 words. One sentence each.
- For the question, rewrite it as a natural question with the same meaning.
Return JSON only: {"question": "...", "claims": ["...", "..."]} with claims in the same order."""

KEEP_RE = re.compile(r"(C?\$[\d,.]+\s*(?:B|M|billion|million)?|\d[\d,.]*\s*(?:%|per cent|basis points)?|"
                     r"\bQ[1-4]\b|\b[1-4]Q\d\d\b|\bH[12]\b|\bFY\d{4}\b|'\d\d\b)")
NAME_RE = re.compile(r"\b[A-Z][a-z]+(?:[A-Z][a-z]+)*(?:\s+[A-Z][a-z]+)*\b")
STOP = {"The", "In", "It", "Agencies", "Industry", "Canadian", "Total", "Average", "Rating", "Falling",
        "Equity", "Trading", "Credit", "Regulators", "One", "A", "An", "Its", "Our", "This", "Who", "What",
        "How", "Which", "When", "Did", "Was", "Is"}


def protected(text):
    nums = [m.group(0).replace(" ", "").rstrip(",.") for m in KEEP_RE.finditer(text)]
    names = [n for n in NAME_RE.findall(text) if n.split()[0] not in STOP]
    return nums, names


def faithful(orig, new):
    """True if the rewrite keeps every protected number/period token and every name, names in the
    same order (so "A acquired B" can't become "B acquired A")."""
    if not new or len(new.split()) > 18:
        return False
    on, onames = protected(orig)
    nn, _ = protected(new)
    if sorted(on) != sorted(nn):
        return False
    pos = []
    for n in onames:
        i = new.find(n)
        if i < 0:
            return False
        pos.append(i)
    return pos == sorted(pos)


def call(client, model, question, claims, tries=4):
    msg = json.dumps({"question": question, "claims": claims}, ensure_ascii=False)
    for k in range(tries):
        try:
            r = client.messages.create(model=model, max_tokens=2000, system=SYSTEM,
                                       messages=[{"role": "user", "content": msg}])
            text = "".join(getattr(b, "text", "") for b in r.content)
            obj = json.loads(re.search(r"\{.*\}", text, re.S).group(0))
            if len(obj.get("claims", [])) != len(claims):
                raise ValueError("claim count changed")
            return obj
        except Exception:
            if k == tries - 1:
                raise
            time.sleep(2 ** k + random.random())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default="data/synthetic.jsonl")
    ap.add_argument("--out", default="data/synthetic_para.jsonl")
    ap.add_argument("--model", default="claude-sonnet-5-5")
    ap.add_argument("--max_questions", type=int, default=3000)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    import anthropic
    client = anthropic.Anthropic()

    groups = defaultdict(list)
    for l in open(args.inp, encoding="utf-8"):
        r = json.loads(l)
        groups[r["qid"]].append(r)
    qids = sorted(groups)
    random.Random(args.seed).shuffle(qids)
    qids = qids[:args.max_questions]
    kept = rejected = 0
    out_rows = []

    def job(q):
        rs = groups[q]
        return q, call(client, args.model, rs[0]["question"], [r["claim"] for r in rs])

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        for i, f in enumerate(as_completed([ex.submit(job, q) for q in qids]), 1):
            try:
                q, obj = f.result()
            except Exception as e:
                print(f"  failed: {type(e).__name__}"); continue
            rs = groups[q]
            new_q = obj.get("question", "")
            new_q = new_q if faithful(rs[0]["question"], new_q) else rs[0]["question"]
            for r, nc in zip(rs, obj["claims"]):
                ok = faithful(r["claim"], nc)
                kept += ok; rejected += not ok
                out_rows.append({**r, "qid": r["qid"] + "-p", "question": new_q, "claim": nc if ok else r["claim"],
                                 "source": "synthetic_v2_para", "paraphrased": ok})
            if i % 100 == 0:
                print(f"  {i}/{len(qids)} questions, rewrites kept {kept:,} / rejected {rejected:,}")
    with open(args.out, "w", encoding="utf-8") as f:
        for r in out_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"wrote {len(out_rows):,} rows -> {args.out}; rewrites kept {kept:,}, rejected {rejected:,} (originals kept)")


if __name__ == "__main__":
    main()
