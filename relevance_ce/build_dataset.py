"""
Assemble every available training source into one mix, enforce the caps, check for leakage,
and write the data catalog.

    python build_dataset.py                 # uses whatever sources exist under data/
    python build_dataset.py --public_share 0.2 --out data/mix/mix.jsonl
    python train_teacher.py --data data/mix/mix.jsonl --init cross-encoder/ettin-reranker-150m-v1 ...

What it does:
  1. Loads each known source if its file exists (see SOURCES); missing ones are listed as TODO.
  2. Tags untagged rows through tagger_hook.py when it is enabled.
  3. Drops exact duplicates (same question + claim), keeping the higher-weight row.
  4. Caps public weak-label data at --public_share of the training rows (proportional per source).
  5. Leakage checks: a qid lives in one split only; a claim text in val/test is removed from train;
     the hold-out set (data/holdout.jsonl) never enters the mix and its questions are removed from it.
  6. Writes data/mix/mix.jsonl, data/mix/manifest.json and data/CATALOG.md (coverage by class and source).
"""
from __future__ import annotations

import argparse
import json
import random
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

LABELS = ["DIRECT", "PARTIAL", "WRONG_INTENT", "WRONG_TIME", "WRONG_RELATION", "ECOSYSTEM", "UNRESOLVED",
          "CONTEXT", "IRRELEVANT"]

# name, path, kind, how it is produced, licence note
SOURCES = [
    ("llm_labeled_real", "data/labeled_real.jsonl", "real", "label_real.py on your pipeline pairs", "yours"),
    ("synthetic_v2", "data/synthetic.jsonl", "synthetic", "generate_synthetic.py (included)", "yours"),
    ("synthetic_v2_para", "data/synthetic_para.jsonl", "synthetic", "paraphrase_synthetic.py", "yours"),
    ("twowiki", "data/public/twowiki.jsonl", "public", "fetch_public.py --sources twowiki", "check repo licence"),
    ("tempreason", "data/public/tempreason.jsonl", "public", "fetch_public.py --sources tempreason", "check dataset card"),
    ("musique", "data/public/musique.jsonl", "public", "fetch_public.py --sources musique", "not stated; check repo"),
    ("hotpotqa", "data/public/hotpotqa.jsonl", "public", "fetch_public.py --sources hotpotqa", "CC BY-SA 4.0 (verify)"),
]
HOLDOUT = ("real_holdout", "data/holdout.jsonl", "holdout", "label_real.py --holdout + your adjudication", "yours")


def load(path):
    return [json.loads(l) for l in open(path, encoding="utf-8")]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/mix/mix.jsonl")
    ap.add_argument("--public_share", type=float, default=0.20)
    ap.add_argument("--synthetic_share", type=float, default=0.0,
                    help="optional cap on synthetic rows once real data exists (0 = no cap)")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    rng = random.Random(args.seed)

    import tagger_hook
    loaded, status = {}, []
    for name, path, kind, how, lic in SOURCES + [HOLDOUT]:
        p = Path(path)
        if p.exists():
            rows = load(p)
            for r in rows:
                r.setdefault("source", name)
                r["_kind"] = kind
                r.setdefault("weight", 1.0)
            loaded[name] = rows
            status.append((name, path, kind, how, lic, len(rows), "ready"))
        else:
            status.append((name, path, kind, how, lic, 0, "TODO"))

    holdout = loaded.pop("real_holdout", [])
    holdout_q = {r["question"].strip().lower() for r in holdout}

    untagged = tagged_now = 0
    for rows in loaded.values():
        for r in rows:
            if not r.get("q_tags") and not r.get("c_tags"):
                if tagger_hook.ENABLED:
                    r["q_tags"] = tagger_hook.tag_question(r["question"])
                    r["c_tags"] = tagger_hook.tag_claim(r["q_tags"], r["claim"])
                    tagged_now += 1
                else:
                    untagged += 1

    # dedup, keep the highest weight
    best = {}
    for rows in loaded.values():
        for r in rows:
            if r["question"].strip().lower() in holdout_q:
                continue
            k = (r["question"].strip().lower(), r["claim"].strip().lower())
            if k not in best or r["weight"] > best[k]["weight"]:
                best[k] = r
    rows = list(best.values())

    # qid -> single split (first seen wins), then remove train claims that also sit in val/test
    qsplit = {}
    for r in rows:
        r["split"] = qsplit.setdefault(r["qid"], r.get("split", "train"))
    # Synthetic data is already split by entity, and its generic CONTEXT/IRRELEVANT claims recur across
    # questions by design, so the claim-text leak check applies to real and public rows only.
    eval_claims = {r["claim"].strip().lower() for r in rows if r["split"] != "train" and r["_kind"] != "synthetic"}
    before = len(rows)
    rows = [r for r in rows if r["split"] != "train" or r["_kind"] == "synthetic"
            or r["claim"].strip().lower() not in eval_claims]
    leak_removed = before - len(rows)

    # caps on train rows
    def cap(kind, share):
        nonlocal rows
        train = [r for r in rows if r["split"] == "train"]
        other_train = sum(1 for r in train if r["_kind"] != kind)
        mine = [r for r in train if r["_kind"] == kind]
        allowed = int(share / (1 - share) * other_train) if share < 1 else len(mine)
        if len(mine) <= allowed:
            return 0
        by_q = defaultdict(list)
        for r in mine:
            by_q[r["qid"]].append(r)
        qids = list(by_q); rng.shuffle(qids)            # drop whole questions, never half a group
        keep, n = set(), 0
        for q in qids:
            if n + len(by_q[q]) > allowed:
                continue
            keep.add(q); n += len(by_q[q])
        dropped = len(mine) - n
        rows = [r for r in rows if not (r["split"] == "train" and r["_kind"] == kind and r["qid"] not in keep)]
        return dropped

    pub_dropped = cap("public", args.public_share) if any(r["_kind"] == "public" for r in rows) else 0
    syn_dropped = cap("synthetic", args.synthetic_share) if args.synthetic_share > 0 else 0

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for r in rows:
            r2 = {k: v for k, v in r.items() if not k.startswith("_")}
            f.write(json.dumps(r2, ensure_ascii=False) + "\n")

    # coverage
    cov = defaultdict(Counter)
    for r in rows:
        cov[r["source"]][r["label"]] += 1
    split_lab = defaultdict(Counter)
    for r in rows:
        split_lab[r["split"]][r["label"]] += 1
    train_kind = Counter(r["_kind"] for r in rows if r["split"] == "train")
    tot_train = sum(train_kind.values()) or 1
    manifest = {"built": str(date.today()), "rows": len(rows), "questions": len({r["qid"] for r in rows}),
                "train_share_by_kind": {k: round(v / tot_train, 3) for k, v in train_kind.items()},
                "by_split": {s: dict(c) for s, c in split_lab.items()}, "by_source": {s: dict(c) for s, c in cov.items()},
                "holdout_rows": len(holdout), "dedup_and_leak_removed": leak_removed,
                "public_rows_capped": pub_dropped, "synthetic_rows_capped": syn_dropped,
                "untagged_rows": untagged, "tagged_by_hook": tagged_now}
    (out.parent / "manifest.json").write_text(json.dumps(manifest, indent=2))

    # catalog
    lines = ["# Training data catalog", "", f"Built {manifest['built']} by `build_dataset.py`. "
             f"Mix: {manifest['rows']:,} rows, {manifest['questions']:,} questions. "
             f"Hold-out: {len(holdout):,} rows (never in the mix).", "",
             "## Sources", "", "| Source | Kind | Status | Rows on disk | Produced by | Licence |", "| --- | --- | --- | --- | --- | --- |"]
    for name, path, kind, how, lic, n, st in status:
        lines.append(f"| {name} | {kind} | {st} | {n:,} | {how} | {lic} |")
    lines += ["", "## Class coverage in the mix (rows)", "",
              "| Source | " + " | ".join(LABELS) + " | Total |", "| --- |" + " --- |" * (len(LABELS) + 1)]
    for s, c in sorted(cov.items()):
        lines.append(f"| {s} | " + " | ".join(f"{c.get(l, 0):,}" for l in LABELS) + f" | {sum(c.values()):,} |")
    tot = Counter()
    for c in cov.values():
        tot.update(c)
    lines.append("| **All** | " + " | ".join(f"**{tot.get(l, 0):,}**" for l in LABELS) + f" | **{sum(tot.values()):,}** |")
    lines += ["", "## Train share by kind", ""] + [f"- {k}: {v:.1%}" for k, v in manifest["train_share_by_kind"].items()]
    gaps = [l for l in LABELS if tot.get(l, 0) and not any(cov[s].get(l) for s in cov if loaded.get(s, [{}])[0].get("_kind") == "real")]
    lines += ["", "## Readiness", "",
              f"- Real labeled data: {'present' if 'llm_labeled_real' in loaded else 'MISSING - run label_real.py'}",
              f"- Real hold-out set: {'present' if holdout else 'MISSING - run label_real.py --holdout'}",
              f"- Untagged rows: {untagged:,}" + ("" if not untagged else " (enable tagger_hook.py to tag them)"),
              f"- Public rows capped: {pub_dropped:,}; duplicate/leaking rows removed: {leak_removed:,}"]
    if "llm_labeled_real" in loaded and gaps:
        lines.append(f"- Classes with no real examples yet: {', '.join(gaps)}")
    Path("data/CATALOG.md").write_text("\n".join(lines) + "\n")

    print(f"mix: {len(rows):,} rows / {manifest['questions']:,} questions -> {out}")
    print("train share by kind:", manifest["train_share_by_kind"])
    print(f"removed: {leak_removed:,} duplicate/leaking, {pub_dropped:,} public over cap; untagged rows {untagged:,}")
    for name, path, kind, how, lic, n, st in status:
        print(f"  [{st:5s}] {name:18s} {n:>9,}  {path}")
    print("catalog -> data/CATALOG.md")


if __name__ == "__main__":
    main()
