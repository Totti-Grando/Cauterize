"""Shared pieces: label set, input formatting, model definition, save/load, metrics."""
from __future__ import annotations

import json
import math
import os
import random
import re
from pathlib import Path

import torch
import torch.nn as nn
import torch.nn.functional as F
from transformers import AutoModel, AutoTokenizer

LABELS = [
    "IRRELEVANT", "UNRESOLVED", "ECOSYSTEM", "WRONG_RELATION", "WRONG_INTENT",
    "WRONG_TIME", "DIRECT", "PARTIAL", "CONTEXT",
]
L2I = {l: i for i, l in enumerate(LABELS)}
UTILITY = {
    "IRRELEVANT": 0.00, "ECOSYSTEM": 0.10, "WRONG_RELATION": 0.15, "WRONG_INTENT": 0.20,
    "UNRESOLVED": 0.25, "WRONG_TIME": 0.30, "CONTEXT": 0.40, "PARTIAL": 0.70, "DIRECT": 1.00,
}
# The relevance call: a claim is RELEVANT if it supplies all or part of the answer.
RELEVANT = {"DIRECT", "PARTIAL"}
SCENARIO = {
    "DIRECT": "Direct answer",
    "PARTIAL": "Partial answer",
    "WRONG_INTENT": "Same entity, wrong intent",
    "WRONG_TIME": "Same entity, wrong time",
    "WRONG_RELATION": "Same topic, wrong relationship",
    "ECOSYSTEM": "Related ecosystem",
    "UNRESOLVED": "Unresolved connection",
    "CONTEXT": "Relevant but unsupported context",
    "IRRELEVANT": "Irrelevant",
}
SCORECARD_ORDER = ["DIRECT", "PARTIAL", "WRONG_INTENT", "WRONG_TIME", "WRONG_RELATION", "ECOSYSTEM",
                   "UNRESOLVED", "CONTEXT", "IRRELEVANT"]
SPECIAL_TOKENS = ["[Q]", "[C]", "[ENT]", "[TIME]", "[ATTR]"]
TAG_RE = re.compile(r"\[(ENT|TIME|ATTR)\]")


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------
def load_jsonl(path, split=None):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            if split is None or r.get("split") == split:
                rows.append(r)
    return rows


def corrupt_tags(tags: str, rng: random.Random, p: float) -> str:
    """Flip some link statuses so the model learns to cross-check tags against text."""
    if p <= 0 or rng.random() > p:
        return tags
    swaps = [("=MATCH", "=NONE"), ("=ADJACENT", "=MATCH"), ("[ENT] UNRESOLVED", "[ENT] NONE"),
             ("=MATCH", "=ADJACENT")]
    a, b = rng.choice(swaps)
    return tags.replace(a, b, 1)


def format_pair(row, rng: random.Random | None = None, tag_dropout=0.0, tag_noise=0.0):
    """Return (query_text, doc_text). Tags dropped together on both sides when dropout fires."""
    q_tags, c_tags = row.get("q_tags", ""), row.get("c_tags", "")
    if rng is not None:
        if rng.random() < tag_dropout:
            q_tags, c_tags = "", ""
        else:
            c_tags = corrupt_tags(c_tags, rng, tag_noise)
    q = f"[Q] {row['question']} {q_tags}".strip()
    c = f"[C] {row['claim']} {c_tags}".strip()
    return q, c


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------
class RelevanceCE(nn.Module):
    """Encoder + Ettin-style head (CLS -> Dense+GELU -> LayerNorm -> Linear(num_labels))."""

    def __init__(self, encoder: nn.Module, hidden: int, num_labels: int = len(LABELS)):
        super().__init__()
        self.encoder = encoder
        self.dense = nn.Linear(hidden, hidden, bias=False)
        self.act = nn.GELU()
        self.norm = nn.LayerNorm(hidden)
        self.out = nn.Linear(hidden, num_labels)
        self.register_buffer("temperature", torch.ones(1))

    def forward(self, input_ids, attention_mask, token_type_ids=None):
        kw = dict(input_ids=input_ids, attention_mask=attention_mask)
        if token_type_ids is not None and "token_type_ids" in self.encoder.forward.__code__.co_varnames:
            kw["token_type_ids"] = token_type_ids
        h = self.encoder(**kw).last_hidden_state[:, 0]
        return self.out(self.norm(self.act(self.dense(h))))


def _find_pretrained(module):
    from transformers import PreTrainedModel
    for m in module.modules():
        if isinstance(m, PreTrainedModel):
            return m
    return None


def build_model(init: str, attn_impl: str | None = None, dtype=None):
    """
    `init` can be:
      - a Sentence Transformers CrossEncoder repo (e.g. cross-encoder/ettin-reranker-150m-v1): the
        relevance-trained encoder is kept, and the Dense(H,H)/LayerNorm head weights are copied
        when shapes match. Requires `pip install sentence-transformers`.
      - a plain encoder repo or local path (e.g. jhu-clsp/ettin-encoder-32m): head starts fresh.
    Returns (model, tokenizer, source_description).
    """
    model_kwargs = {}
    if attn_impl:
        model_kwargs["attn_implementation"] = attn_impl
    try:
        from sentence_transformers import CrossEncoder
        ce = CrossEncoder(init, model_kwargs=model_kwargs) if model_kwargs else CrossEncoder(init)
        enc = _find_pretrained(ce)
        if enc is None:
            raise RuntimeError("no transformers model inside CrossEncoder")
        tok = ce.tokenizer
        hidden = enc.config.hidden_size
        model = RelevanceCE(enc, hidden)
        copied = []
        for name, mod in ce.named_modules():
            if mod is enc or any(mod is m for m in enc.modules()):
                continue
            if isinstance(mod, nn.Linear) and tuple(mod.weight.shape) == (hidden, hidden) and "dense" not in copied:
                model.dense.weight.data.copy_(mod.weight.data); copied.append("dense")
            if isinstance(mod, nn.LayerNorm) and mod.weight.shape[0] == hidden and "norm" not in copied:
                model.norm.load_state_dict(mod.state_dict()); copied.append("norm")
        src = f"CrossEncoder {init} (head layers copied: {copied or 'none'})"
    except Exception as e:  # plain encoder path
        enc = AutoModel.from_pretrained(init, **model_kwargs)
        tok = AutoTokenizer.from_pretrained(init)
        model = RelevanceCE(enc, enc.config.hidden_size)
        src = f"plain encoder {init} ({type(e).__name__}: {str(e)[:80]})"
    added = tok.add_special_tokens({"additional_special_tokens": SPECIAL_TOKENS})
    if added:
        model.encoder.resize_token_embeddings(len(tok))
    if dtype is not None:
        model.to(dtype)
    return model, tok, src


def save_model(model: RelevanceCE, tok, out_dir, extra: dict | None = None):
    out = Path(out_dir)
    (out / "encoder").mkdir(parents=True, exist_ok=True)
    model.encoder.save_pretrained(out / "encoder")
    tok.save_pretrained(out / "encoder")
    head = {k: v for k, v in model.state_dict().items() if not k.startswith("encoder.")}
    torch.save(head, out / "head.pt")
    meta = {"labels": LABELS, "utility": UTILITY, "hidden": model.dense.in_features,
            "temperature": float(model.temperature.item())}
    meta.update(extra or {})
    (out / "meta.json").write_text(json.dumps(meta, indent=2))


def load_model(model_dir, device="cpu", attn_impl=None):
    d = Path(model_dir)
    meta = json.loads((d / "meta.json").read_text())
    kw = {"attn_implementation": attn_impl} if attn_impl else {}
    enc = AutoModel.from_pretrained(d / "encoder", **kw)
    tok = AutoTokenizer.from_pretrained(d / "encoder")
    model = RelevanceCE(enc, meta["hidden"], len(meta["labels"]))
    model.load_state_dict(torch.load(d / "head.pt", map_location="cpu"), strict=False)
    return model.to(device).eval(), tok, meta


# ---------------------------------------------------------------------------
# Batching
# ---------------------------------------------------------------------------
def encode_batch(tok, pairs, max_length, device):
    q, c = zip(*pairs)
    enc = tok(list(q), list(c), padding=True, truncation="longest_first", max_length=max_length,
              return_tensors="pt")
    return {k: v.to(device) for k, v in enc.items()}


@torch.no_grad()
def predict_logits(model, tok, rows, max_length=128, batch_size=256, device="cpu", use_tags=True):
    model.eval()
    out = []
    for i in range(0, len(rows), batch_size):
        chunk = rows[i:i + batch_size]
        pairs = [format_pair(r if use_tags else {**r, "q_tags": "", "c_tags": ""}) for r in chunk]
        b = encode_batch(tok, pairs, max_length, device)
        with torch.autocast(device_type="cuda", dtype=torch.bfloat16, enabled=(device == "cuda")):
            out.append(model(**b).float().cpu())
    return torch.cat(out) if out else torch.empty(0, len(LABELS))


def utilities_tensor():
    return torch.tensor([UTILITY[l] for l in LABELS])


def expected_utility(probs: torch.Tensor) -> torch.Tensor:
    """Probability-weighted utility. Kept for analysis only; not used for scoring."""
    return probs @ utilities_tensor()


# Utility tiers are at least 0.05 apart, so a confidence tie-break scaled by 0.01 can never
# move a claim across tiers: it only orders claims that share the same top label.
TIEBREAK = 0.01


def top_class_score(probs: torch.Tensor) -> torch.Tensor:
    """Relevance = utility of the most likely class; confidence only breaks ties within a tier."""
    conf, idx = probs.max(-1)
    return utilities_tensor()[idx] + TIEBREAK * conf


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------
def evaluate(logits: torch.Tensor, rows, temperature: float = 1.0):
    y = torch.tensor([L2I[r["label"]] for r in rows])
    probs = F.softmax(logits / temperature, dim=-1)
    pred = probs.argmax(-1)
    acc = (pred == y).float().mean().item()
    per_class, f1s = {}, []
    for i, l in enumerate(LABELS):
        tp = ((pred == i) & (y == i)).sum().item()
        fp = ((pred == i) & (y != i)).sum().item()
        fn = ((pred != i) & (y == i)).sum().item()
        if tp + fn == 0:
            continue
        p = tp / (tp + fp) if tp + fp else 0.0
        r = tp / (tp + fn)
        f1 = 2 * p * r / (p + r) if p + r else 0.0
        per_class[l] = {"p": round(p, 3), "r": round(r, 3), "f1": round(f1, 3), "n": tp + fn}
        f1s.append(f1)
    # minimal-pair accuracy: in each question group, every DIRECT must outscore every non-DIRECT
    score = top_class_score(probs)
    groups: dict[str, list[int]] = {}
    for i, r in enumerate(rows):
        groups.setdefault(r["qid"], []).append(i)
    wins = total = 0
    for idx in groups.values():
        d = [i for i in idx if rows[i]["label"] == "DIRECT"]
        o = [i for i in idx if rows[i]["label"] != "DIRECT"]
        for a in d:
            for b in o:
                total += 1
                wins += int(score[a] > score[b])
    # expected calibration error on the argmax class, 10 bins
    conf = probs.max(-1).values
    ece = 0.0
    for lo in [i / 10 for i in range(10)]:
        m = (conf > lo) & (conf <= lo + 0.1)
        if m.any():
            ece += m.float().mean().item() * abs((pred[m] == y[m]).float().mean().item() - conf[m].mean().item())
    # precision of DIRECT labels (what a downstream consumer would trust as "answers it")
    sel = pred == L2I["DIRECT"]
    p_dir = ((y[sel] == L2I["DIRECT"]).float().mean().item()) if sel.any() else None
    # share of claims whose top label is uncertain (confidence < 0.5): candidates for review
    uncertain = (conf < 0.5).float().mean().item()
    sc = scorecard([LABELS[i] for i in pred.tolist()], rows)
    return {"scorecard": sc,
            "accuracy": round(acc, 4), "macro_f1": round(sum(f1s) / len(f1s), 4),
            "pair_accuracy": round(wins / total, 4) if total else float("nan"),
            "ndcg@5": round(ndcg_at_k(score.tolist(), rows, 5), 4),
            "ece": round(ece, 4), "direct_precision": round(p_dir, 4) if p_dir is not None else None,
            "predicted_direct": int(sel.sum()), "uncertain_share": round(uncertain, 4),
            "per_class": per_class}


def scorecard(pred_labels, rows):
    """
    The main test: one row per scenario, two error directions weighted equally.

    For relevant scenarios (DIRECT, PARTIAL), `error` = missed: labeled as not relevant.
    For every other scenario, `error` = fooled: labeled DIRECT or PARTIAL.
    `named` = share labeled with exactly the right scenario (is the explanation right).
    `mistaken_for` = the most common wrong label for that scenario.
    Headline: missed rate over all relevant claims, fooled rate over all non-relevant claims,
    and balanced accuracy = mean of (1 - missed) and (1 - fooled), so neither error can hide
    behind the other however many claims of each kind there are.
    """
    from collections import Counter
    by = {}
    for p, r in zip(pred_labels, rows):
        by.setdefault(r["label"], []).append(p)
    table = []
    for g in SCORECARD_ORDER:
        preds = by.get(g, [])
        if not preds:
            continue
        rel = g in RELEVANT
        err = sum((p not in RELEVANT) if rel else (p in RELEVANT) for p in preds) / len(preds)
        wrong = Counter(p for p in preds if p != g).most_common(1)
        table.append({"scenario": SCENARIO[g], "label": g, "n": len(preds),
                      "error_type": "missed" if rel else "fooled", "error": round(err, 4),
                      "named": round(sum(p == g for p in preds) / len(preds), 4),
                      "mistaken_for": wrong[0][0] if wrong else None})
    gold_rel = [r["label"] in RELEVANT for r in rows]
    pred_rel = [p in RELEVANT for p in pred_labels]
    n_rel = sum(gold_rel); n_non = len(rows) - n_rel
    missed = sum(g and not p for g, p in zip(gold_rel, pred_rel)) / n_rel if n_rel else None
    fooled = sum((not g) and p for g, p in zip(gold_rel, pred_rel)) / n_non if n_non else None
    bal = (1 - missed + 1 - fooled) / 2 if missed is not None and fooled is not None else None
    return {"missed_rate": round(missed, 4) if missed is not None else None,
            "fooled_rate": round(fooled, 4) if fooled is not None else None,
            "balanced_accuracy": round(bal, 4) if bal is not None else None,
            "relevant_claims": n_rel, "non_relevant_claims": n_non, "rows": table}


def format_scorecard(sc, title="Relevance scorecard"):
    lines = [title,
             f"  missed {sc['missed_rate']:.1%} of {sc['relevant_claims']:,} relevant claims | "
             f"fooled on {sc['fooled_rate']:.1%} of {sc['non_relevant_claims']:,} non-relevant | "
             f"balanced accuracy {sc['balanced_accuracy']:.1%}",
             f"  {'Scenario':34s} {'n':>6s}  {'error':>13s}  {'named':>6s}  mistaken for"]
    for r in sc["rows"]:
        lines.append(f"  {r['scenario']:34s} {r['n']:6,d}  {r['error_type']:>6s} {r['error']:6.1%}  "
                     f"{r['named']:6.1%}  {r['mistaken_for'] or '-'}")
    return "\n".join(lines)


def ndcg_at_k(scores, rows, k=5):
    """Mean NDCG@k per question, gains = gold class utilities. Works for any scorer."""
    groups: dict[str, list[int]] = {}
    for i, r in enumerate(rows):
        groups.setdefault(r["qid"], []).append(i)
    vals = []
    for idx in groups.values():
        gains = [UTILITY[rows[i]["label"]] for i in idx]
        order = sorted(range(len(idx)), key=lambda j: -scores[idx[j]])
        dcg = sum(gains[j] / math.log2(rank + 2) for rank, j in enumerate(order[:k]))
        ideal = sum(g / math.log2(rank + 2) for rank, g in enumerate(sorted(gains, reverse=True)[:k]))
        if ideal > 0:
            vals.append(dcg / ideal)
    return sum(vals) / len(vals) if vals else float("nan")


def fit_temperature(logits: torch.Tensor, rows) -> float:
    """Single-parameter temperature scaling on held-out logits (Guo et al., 2017)."""
    y = torch.tensor([L2I[r["label"]] for r in rows])
    log_t = torch.zeros(1, requires_grad=True)
    opt = torch.optim.LBFGS([log_t], lr=0.1, max_iter=100)

    def closure():
        opt.zero_grad()
        loss = F.cross_entropy(logits / log_t.exp(), y)
        loss.backward()
        return loss

    opt.step(closure)
    return float(log_t.exp().item())


def set_seed(seed):
    random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def lr_lambda(warmup, total):
    def f(step):
        if step < warmup:
            return step / max(1, warmup)
        return max(0.0, (total - step) / max(1, total - warmup))
    return f
