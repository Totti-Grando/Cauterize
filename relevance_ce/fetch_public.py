"""
Download public datasets and convert them into 9-class (question, claim, label) rows.
Run on your own machine (needs huggingface.co; 2Wiki and MuSiQue come as zip files you download).

    pip install datasets
    python fetch_public.py --inspect                                  # print each source's schema
    python fetch_public.py --sources hotpotqa tempreason              # HF sources, downloaded for you
    python fetch_public.py --sources twowiki --twowiki_dir raw/2wiki  # after unzipping data.zip
    python fetch_public.py --sources musique --musique_dir raw/musique

Where the raw files come from:
  twowiki   https://www.dropbox.com/s/npidmtadreo6df2/data.zip  (unzip -> train.json, dev.json)
            linked from https://github.com/Alab-NII/2wikimultihop
  musique   linked from https://github.com/stonybrooknlp/musique  (musique_ans_v1.0_*.jsonl,
            musique_full_v1.0_*.jsonl)
  tempreason  Hugging Face: tonytan48/TempReason
  hotpotqa    Hugging Face: hotpotqa/hotpot_qa (distractor)

Every converted row carries `source` and a `weight` below 1.0, because the labels come from
dataset structure, not from a human reading the pair. Claims longer than --max_words are dropped
to stay near your 5-10 word claims. Tags are left empty; build_dataset.py runs your entity
tagger over them (see tagger_hook.py) so public rows look like your real rows.

What each converter produces:
  twowiki     answer-bearing triple -> DIRECT; bridge / comparison triples -> PARTIAL;
              triple read backwards -> WRONG_RELATION; same (subject, object) with a different
              relation -> WRONG_RELATION; another true triple about the same subject ->
              WRONG_INTENT; a triple from an unrelated question -> IRRELEVANT
  tempreason  fact whose span covers the question's date -> DIRECT; same subject and relation,
              other span -> WRONG_TIME; fact from another question -> IRRELEVANT
  musique     final-hop supporting sentence with the answer -> DIRECT; other supporting-hop
              sentences -> PARTIAL; distractor-paragraph sentences -> IRRELEVANT (low weight)
  hotpotqa    supporting sentence with the answer -> DIRECT; other supporting -> PARTIAL;
              other gold-page sentences -> WRONG_INTENT; distractor pages -> IRRELEVANT
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
from collections import Counter, defaultdict
from pathlib import Path

UTIL = {"IRRELEVANT": 0.0, "ECOSYSTEM": 0.1, "WRONG_RELATION": 0.15, "WRONG_INTENT": 0.2,
        "UNRESOLVED": 0.25, "WRONG_TIME": 0.3, "CONTEXT": 0.4, "PARTIAL": 0.7, "DIRECT": 1.0}


def split_for(key: str) -> str:
    h = int(hashlib.md5(key.encode()).hexdigest(), 16) % 100
    return "train" if h < 80 else ("val" if h < 90 else "test")


def row(qid, question, claim, label, source, weight, split_key, pert=""):
    return {"qid": qid, "question": question.strip(), "q_tags": "", "claim": claim.strip(), "c_tags": "",
            "label": label, "utility": UTIL[label], "perturbation": pert, "split": split_for(split_key),
            "weight": weight, "source": source}


def short_enough(text, max_words):
    return 3 <= len(text.split()) <= max_words


def write_rows(rows, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    c = Counter(r["label"] for r in rows)
    print(f"  wrote {len(rows):,} rows / {len({r['qid'] for r in rows}):,} questions -> {path}")
    print(f"  labels: {dict(sorted(c.items(), key=lambda x: -x[1]))}")


# ---------------------------------------------------------------------------
# 2WikiMultihopQA  (HotpotQA format + `evidences` triples [subject, relation, object])
# ---------------------------------------------------------------------------
REL_TEMPLATES = {
    "director": "{s} was directed by {o}.",
    "producer": "{s} was produced by {o}.",
    "composer": "{s} was composed by {o}.",
    "performer": "{s} was performed by {o}.",
    "father": "{o} is the father of {s}.",
    "mother": "{o} is the mother of {s}.",
    "spouse": "{s} was married to {o}.",
    "child": "{o} is a child of {s}.",
    "sibling": "{s} is a sibling of {o}.",
    "date of birth": "{s} was born on {o}.",
    "date of death": "{s} died on {o}.",
    "place of birth": "{s} was born in {o}.",
    "place of death": "{s} died in {o}.",
    "country of citizenship": "{s} was a citizen of {o}.",
    "country of origin": "{s} originates from {o}.",
    "country": "{s} is located in {o}.",
    "publication date": "{s} was released on {o}.",
    "inception": "{s} was founded on {o}.",
    "founded by": "{s} was founded by {o}.",
    "educated at": "{s} was educated at {o}.",
    "employer": "{s} worked for {o}.",
    "occupation": "{s} worked as a {o}.",
    "award received": "{s} received the {o}.",
    "cause of death": "{s} died of {o}.",
    "place of burial": "{s} was buried in {o}.",
    "manufacturer": "{s} was made by {o}.",
    "located in the administrative territorial entity": "{s} is in {o}.",
}
SYMMETRIC = {"spouse", "sibling"}
# Relations whose subject and object are the same kind of thing: only these can be read backwards
# and still make a plausible (wrong) claim.
REVERSIBLE = {"father", "mother", "child"}
# Swaps stay inside a type group, so the wrong relation is plausible, not nonsense.
REL_GROUPS = [
    {"father", "mother", "child", "spouse", "sibling"},
    {"director", "producer", "composer", "performer", "screenwriter"},
    {"place of birth", "place of death", "place of burial"},
    {"date of birth", "date of death"},
    {"founded by", "employer", "educated at"},
]
DATE_RE = re.compile(r"\b(1[0-9]{3}|20[0-9]{2})\b")


def verbalize(s, r, o):
    t = REL_TEMPLATES.get(r)
    return t.format(s=s, o=o) if t else f"The {r} of {s} is {o}."


def is_value(o):
    """Dates, numbers: reversing a triple with a value object is nonsense, so skip those."""
    return bool(DATE_RE.search(o)) or o.replace(",", "").replace(".", "").isdigit()


def load_twowiki(d: Path):
    out = []
    for name in ("train.json", "dev.json"):
        p = d / name
        if p.exists():
            out += json.loads(p.read_text(encoding="utf-8"))
            print(f"  loaded {p}")
    return out


def convert_twowiki(samples, max_words=20, max_q=40000, seed=7):
    rng = random.Random(seed)
    by_subject = defaultdict(set)
    rel_pool = Counter()
    for ex in samples:
        for s, r, o in ex.get("evidences", []) or []:
            by_subject[s].add((s, r, o))
            if not is_value(o):
                rel_pool[r] += 1
    group_of = {r: g for g in REL_GROUPS for r in g}
    all_triples = [t for ts in by_subject.values() for t in ts]
    rows, used = [], 0
    for ex in samples:
        ev = ex.get("evidences") or []
        ans = str(ex.get("answer", "")).strip()
        if not ev or not ans:
            continue
        used += 1
        if used > max_q:
            break
        qid, q, qtype = f"2wiki-{ex['_id']}", ex["question"], ex.get("type", "")
        key = ex.get("entity_ids") or qid
        own = {tuple(t) for t in ev}
        subjects = {t[0] for t in ev} | {t[2] for t in ev}
        seen = set()

        def add(label, claim, w, pert):
            if short_enough(claim, max_words) and claim not in seen:
                seen.add(claim)
                rows.append(row(qid, q, claim, label, "twowiki", w, key, pert))

        compare = qtype in ("comparison", "bridge_comparison", "bridge-comparison")
        for s, r, o in ev:
            final = (not compare) and ans.lower() == o.lower()
            add("DIRECT" if final else "PARTIAL", verbalize(s, r, o), 0.6, "evidence")
        for s, r, o in ev:
            if r in REVERSIBLE and o != s:
                add("WRONG_RELATION", verbalize(o, r, s), 0.6, "relation_reversed")
            alts = sorted(group_of.get(r, set()) - {r})
            if alts:
                r2 = rng.choice(alts)
                if (s, r2, o) not in by_subject.get(s, ()):        # don't emit a swap that is actually true
                    add("WRONG_RELATION", verbalize(s, r2, o), 0.45, "relation_swapped")
            other = [t for t in by_subject.get(s, ()) if t not in own and t[1] != r]
            if other:
                add("WRONG_INTENT", verbalize(*rng.choice(sorted(other))), 0.6, "same_subject_other_attribute")
        for _ in range(2):
            t = rng.choice(all_triples)
            if t[0] not in subjects and t[2] not in subjects:
                add("IRRELEVANT", verbalize(*t), 0.5, "unrelated_triple")
    return rows


# ---------------------------------------------------------------------------
# TempReason (L2/L3: question at a date, `fact_context` lines with spans, `text_answers`, `neg_answers`)
# ---------------------------------------------------------------------------
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep",
                                      "oct", "nov", "dec"], 1)}
MON_YEAR = r"([A-Za-z]{3})[a-z]*\.?,?\s+(\d{4})"
SPAN_RE = re.compile(rf"from\s+{MON_YEAR}\s+to\s+{MON_YEAR}", re.I)
QDATE_RE = re.compile(rf"(?:in|on|at|during|as of)\s+{MON_YEAR}", re.I)


def ym(mon, year):
    m = MONTHS.get(mon[:3].lower())
    return int(year) * 12 + (m or 1) - 1 if m else None


def parse_facts(fact_context):
    if isinstance(fact_context, list):
        lines = fact_context
    else:
        lines = re.split(r"\n+|(?<=\.)\s+(?=[A-Z])", fact_context or "")
    for line in lines:
        m = SPAN_RE.search(line)
        if m:
            a, b = ym(m[1], m[2]), ym(m[3], m[4])
            if a is not None and b is not None:
                yield line.strip(), a, b


def convert_tempreason(ds_rows, max_words=24, max_q=40000, seed=7):
    rng = random.Random(seed)
    rows, skipped, pool = [], Counter(), []
    for i, ex in enumerate(ds_rows):
        if i >= max_q:
            break
        q = ex.get("question", "")
        qd = QDATE_RE.search(q)
        facts = list(parse_facts(ex.get("fact_context") or ""))
        if not qd or not facts:
            skipped["no_date_or_facts"] += 1
            continue
        t = ym(qd[1], qd[2])
        answers = [a.lower() for a in (ex.get("text_answers") or {}).get("text", [])]
        negs = [a.lower() for a in (ex.get("neg_answers") or [])]
        qid = f"tempreason-{ex.get('id', i)}"
        for line, a, b in facts:
            covers = a <= t <= b
            has_ans = any(x and x in line.lower() for x in answers)
            has_neg = any(x and x in line.lower() for x in negs)
            if covers and (has_ans or not answers):
                label = "DIRECT"
            elif not covers and (has_neg or not has_ans):
                label = "WRONG_TIME"
            else:
                skipped["span_answer_disagree"] += 1   # structure and answers disagree: drop
                continue
            if short_enough(line, max_words):
                rows.append(row(qid, q, line, label, "tempreason", 0.6, qid, "span_check"))
                pool.append((qid, line))
    by_q = defaultdict(list)
    for r in rows:
        by_q[r["qid"]].append(r)
    for qid, rs in by_q.items():
        for _ in range(2):
            oq, line = rng.choice(pool)
            if oq != qid:
                rows.append(row(qid, rs[0]["question"], line, "IRRELEVANT", "tempreason", 0.5, qid,
                                "other_question_fact"))
    if skipped:
        print(f"  skipped: {dict(skipped)}")
    return rows


# ---------------------------------------------------------------------------
# MuSiQue (jsonl: paragraphs[{title, paragraph_text, is_supporting}], question_decomposition[{answer,
# paragraph_support_idx}], question, answer, answerable)
# ---------------------------------------------------------------------------
SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'])")


PRONOUN_RE = re.compile(r"^(It|He|She|They|The company|The firm)\b\s*", re.I)


def convert_musique(lines, max_words=22, max_q=40000, seed=7):
    """Uses each hop's paragraph_support_idx, so a sentence is PARTIAL only if it sits in the
    paragraph that hop is answered from AND contains that hop's answer."""
    rng = random.Random(seed)
    rows = []
    for i, ex in enumerate(lines):
        if i >= max_q:
            break
        q, ans = ex["question"], str(ex.get("answer", "")).strip().lower()
        qid = f"musique-{ex['id']}"
        paras = ex.get("paragraphs", [])
        hop_by_para = {}
        decomp = ex.get("question_decomposition") or []
        for k, h in enumerate(decomp):
            idx = h.get("paragraph_support_idx")
            if idx is not None:
                hop_by_para[idx] = (k, str(h.get("answer", "")).strip().lower(), k == len(decomp) - 1)
        answerable = ex.get("answerable", True)
        seen = set()

        def add(label, claim, w, pert):
            if short_enough(claim, max_words) and claim not in seen:
                seen.add(claim)
                rows.append(row(qid, q, claim, label, "musique", w, qid, pert))

        for pi, p in enumerate(paras):
            title = p.get("title", "").strip()
            sents = SENT_SPLIT.split(p.get("paragraph_text", ""))
            if pi in hop_by_para:
                _, hop_ans, last = hop_by_para[pi]
                for s in sents:
                    resolved = PRONOUN_RE.sub(title + " ", s, count=1) if title else s
                    if hop_ans and hop_ans in s.lower():
                        label = "DIRECT" if (last and answerable and ans and ans in s.lower()) else "PARTIAL"
                        add(label, resolved, 0.5, "final_hop" if label == "DIRECT" else "intermediate_hop")
                        if resolved != s:
                            add("UNRESOLVED", s, 0.4, "pronoun_subject")
                    else:
                        add("WRONG_INTENT", resolved, 0.4, "support_paragraph_other_sentence")
            elif not p.get("is_supporting"):
                for s in rng.sample(sents, k=min(1, len(sents))):
                    add("IRRELEVANT", s, 0.2, "distractor")
    return rows


# ---------------------------------------------------------------------------
# HotpotQA (distractor)
# ---------------------------------------------------------------------------
def convert_hotpot(ds, max_q=20000, max_words=25):
    rows = []
    for i, ex in enumerate(ds):
        if i >= max_q:
            break
        q, ans = ex["question"], ex["answer"].strip().lower()
        sup = set(zip(ex["supporting_facts"]["title"], ex["supporting_facts"]["sent_id"]))
        gold = {t for t, _ in sup}
        qid = f"hotpot-{ex['id']}"
        key = sorted(gold)[0] if gold else qid
        for title, sents in zip(ex["context"]["title"], ex["context"]["sentences"]):
            for j, s in enumerate(sents):
                s = s.strip()
                if not short_enough(s, max_words):
                    continue
                if (title, j) in sup:
                    label = "DIRECT" if ans and ans in s.lower() and ans not in ("yes", "no") else "PARTIAL"
                    w = 0.4
                elif title in gold:
                    label, w = "WRONG_INTENT", 0.3
                else:
                    label, w = "IRRELEVANT", 0.3
                rows.append(row(qid, q, s, label, "hotpotqa", w, key, "structure"))
    return rows


# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/public")
    ap.add_argument("--sources", nargs="+", default=["hotpotqa", "tempreason"],
                    choices=["hotpotqa", "tempreason", "twowiki", "musique"])
    ap.add_argument("--twowiki_dir", default="raw/2wiki")
    ap.add_argument("--musique_dir", default="raw/musique")
    ap.add_argument("--max_q", type=int, default=40000)
    ap.add_argument("--inspect", action="store_true")
    args = ap.parse_args()
    out = Path(args.out)

    for src in args.sources:
        print(f"[{src}]")
        if src == "twowiki":
            samples = load_twowiki(Path(args.twowiki_dir))
            if not samples:
                print(f"  no train.json/dev.json in {args.twowiki_dir}: download data.zip (see docstring)")
                continue
            if args.inspect:
                print(json.dumps(samples[0], default=str)[:1500]); continue
            write_rows(convert_twowiki(samples, max_q=args.max_q), out / "twowiki.jsonl")
        elif src == "musique":
            files = sorted(Path(args.musique_dir).glob("musique_*train*.jsonl"))
            lines = [json.loads(l) for f in files for l in f.open(encoding="utf-8")]
            if not lines:
                print(f"  no musique_*train*.jsonl in {args.musique_dir}"); continue
            if args.inspect:
                print(json.dumps(lines[0], default=str)[:1500]); continue
            write_rows(convert_musique(lines, max_q=args.max_q), out / "musique.jsonl")
        else:
            from datasets import load_dataset
            repo, cfg = {"hotpotqa": ("hotpotqa/hotpot_qa", "distractor"),
                         "tempreason": ("tonytan48/TempReason", None)}[src]
            try:
                ds = load_dataset(repo, cfg) if cfg else load_dataset(repo)
            except Exception as e:
                print(f"  could not load {repo}: {type(e).__name__}: {str(e)[:200]}")
                if src == "tempreason":
                    print("  TempReason has several files; try: git lfs install && "
                          "git clone https://huggingface.co/datasets/tonytan48/TempReason raw/tempreason "
                          "then load the L2/L3 json files with datasets.load_dataset('json', data_files=...)")
                continue
            split = ds["train"]
            if args.inspect:
                print(f"  {ds}\n  first row: {json.dumps(split[0], default=str)[:1500]}"); continue
            conv = convert_hotpot if src == "hotpotqa" else convert_tempreason
            write_rows(conv(split, max_q=args.max_q), out / f"{src}.jsonl")


if __name__ == "__main__":
    main()
