"""Nodal claim scoring: a claim DAG with per-node truthfulness rollups.

This is an ADDITIVE layer — it never touches the frozen contracts (``BinaryQuestion``,
``AuditRecord``, ``Verdict``). It computes a separate claim tree whose nodes carry their own
sub-scores and a composite ``score`` derived bottom-up. A run that never builds a claim tree is
unaffected; this is the same "extend, don't modify" discipline as ``AuditRecord → AssuranceRecord``.

Node kinds and their scoring (locked with the user):

* **anchored** — a claim grounded directly in a source. Three truthfulness sub-scores:
  ``groundedness``, ``source_attribution``, ``source_quality``. Its score is the WEAKEST LINK::

      score = min(groundedness, source_attribution, source_quality)

* **derived** — a claim reasoned from parent claims. Its *logical completeness* (reasoning fidelity)
  can lift it, but ONLY if its premises are trustworthy enough to reason from — the *axiom gate*::

      m = min( load-bearing parents' scores )          # OR-groups reduced by max; non-load-bearing excluded
      if m >= AXIOM_THRESHOLD:   score = max(logical_completeness, min(truthfulness))   # axiom-grade premises: good logic can exceed thin grounding
      else:                      score = min(truthfulness)                              # premises below axiom: logical completeness is INVALID, dropped

  where ``min(truthfulness) = min(groundedness, source_attribution, source_quality)`` (the claim's
  own weakest link) and ``logical_completeness = reasoning_fidelity``. This is why ``max`` is SAFE: it
  can only lift a claim when ALL its load-bearing premises are already axiom-grade (m >= 0.75), so
  coherent-but-unsupported reasoning cannot launder itself green. Below the gate, logical completeness
  is discarded entirely — reasoning from weak premises is meaningless.

* **orphan** — no source anchor, no load-bearing parents, no reasoning. Its value collapses to
  relevance. Relevance is a STUB here (``relevance`` field, defaulting to an abstain) to be sharpened
  later; the rollup treats it as the score.

Load-bearing AND/OR (the "and/or relations" from the original ask): a parent link is ``load_bearing``
when the premise is independently necessary (AND). Parents sharing an ``or_group`` are alternatives
(OR) — the group contributes its ``max`` (best available). Non-load-bearing parents are excluded from
the gate entirely.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

AXIOM_THRESHOLD = 0.75          # load-bearing parents at/above this are treated as axioms (tunable)

# Display bands (independent of the gate threshold; purely for coloring the node).
_BAND_GREEN, _BAND_AMBER = 0.75, 0.5


@dataclass
class ParentLink:
    """A derived claim's dependency on a parent claim.

    ``load_bearing`` — the premise is independently necessary (an AND term). Only load-bearing
    parents feed the axiom gate. ``or_group`` — parents sharing a group id are alternatives (OR);
    the group is reduced by ``max`` (best available) before entering the gate ``min``.
    """

    parent_id: str
    load_bearing: bool = True
    or_group: Optional[str] = None
    relation: str = ""          # optional natural-language description of the link (e.g. "because revenue rose")


@dataclass
class ClaimNode:
    id: str
    text: str
    kind: str = "anchored"                       # anchored | derived | orphan
    # truthfulness sub-scores (anchored uses all three; derived measures its own where it can)
    groundedness: Optional[float] = None
    source_attribution: Optional[float] = None
    source_quality: Optional[float] = None
    # derived-only signals
    reasoning_fidelity: Optional[float] = None    # entailed reasoning steps / total (0..1)
    parents: list[ParentLink] = field(default_factory=list)
    # orphan-only (STUB — relevance to be enhanced later)
    relevance: Optional[float] = None
    # corpus link: the source id this claim grounded against (set by the retrieval binder), for the graph
    grounded_source: Optional[str] = None
    # --- computed by score_tree (do not set by hand) ---
    own_truthfulness: Optional[float] = None      # min of the three sub-scores
    parent_min: Optional[float] = None            # m — the axiom gate value
    score: Optional[float] = None
    branch: str = ""                              # which rule fired, for the audit trail / tooltip
    note: str = ""


def _min_defined(*vals: Optional[float]) -> Optional[float]:
    present = [v for v in vals if v is not None]
    return min(present) if present else None


def _own_truthfulness(n: ClaimNode) -> Optional[float]:
    """min of whichever of the three truthfulness sub-scores are present (the weakest link)."""
    return _min_defined(n.groundedness, n.source_attribution, n.source_quality)


def _gate_value(node: ClaimNode, scored: dict[str, float]) -> Optional[float]:
    """m = min over load-bearing parents; OR-groups reduced by max; non-load-bearing excluded."""
    loose: list[float] = []
    groups: dict[str, list[float]] = {}
    for link in node.parents:
        if not link.load_bearing:
            continue
        ps = scored.get(link.parent_id)
        if ps is None:
            continue
        if link.or_group:
            groups.setdefault(link.or_group, []).append(ps)
        else:
            loose.append(ps)
    contributions = loose + [max(g) for g in groups.values() if g]
    return min(contributions) if contributions else None


def _score_node(node: ClaimNode, scored: dict[str, float]) -> None:
    """Fill node.score/own_truthfulness/parent_min/branch from already-scored parents."""
    own = _own_truthfulness(node)
    node.own_truthfulness = own

    if node.kind == "orphan":
        node.score = node.relevance
        node.branch = "orphan:relevance"
        node.note = "no anchor/parents/reasoning — relevance stub (enhance later)"
        return

    if node.kind == "anchored":
        node.score = own
        node.branch = "anchored:min(3)"
        return

    # derived — score = max(logical_completeness, min(truthfulness)) IFF all load-bearing parents are
    # axiom-grade (m >= AXIOM_THRESHOLD); otherwise logical completeness is invalid -> min(truthfulness).
    m = _gate_value(node, scored)
    node.parent_min = m
    lc = node.reasoning_fidelity            # logical completeness
    truth = own                             # min(truthfulness) = min of the present sub-scores

    if m is None:
        # tagged derived but has no usable load-bearing parents — degenerate. Fall back to whatever
        # the claim can stand on itself (own truthfulness, else logical completeness, else abstain).
        node.score = truth if truth is not None else lc
        node.branch = "derived:no-parents→self"
        node.note = "derived claim with no load-bearing parents; scored on its own signals"
        return

    if m >= AXIOM_THRESHOLD:
        # premises are axiom-grade -> logical completeness is VALID and may lift the claim
        cands = [v for v in (lc, truth) if v is not None]
        node.score = max(cands) if cands else m
        node.branch = f"derived:axiom(m={m:.2f}≥{AXIOM_THRESHOLD})→max(logical_completeness, min_truthfulness)"
    else:
        # premises below axiom -> logical completeness INVALID, dropped; claim stands on truthfulness
        node.score = truth if truth is not None else m
        node.branch = f"derived:below-axiom(m={m:.2f}<{AXIOM_THRESHOLD})→min_truthfulness"
        node.note = "load-bearing premises below axiom threshold; logical completeness discarded"


def score_tree(nodes: dict[str, ClaimNode]) -> dict[str, ClaimNode]:
    """Score every node bottom-up (parents before children), in place. Cycle-safe.

    Returns the same dict for convenience. A dependency cycle is broken defensively: a node still
    waiting on an unresolved (cyclic) parent is scored with whatever parents ARE resolved, and the
    back-edge is ignored, so scoring always terminates and never raises on malformed input.
    """
    scored: dict[str, float] = {}
    visiting: set[str] = set()
    order: list[str] = []

    def visit(nid: str) -> None:
        if nid in scored or nid not in nodes:
            return
        if nid in visiting:
            return  # cycle back-edge — skip; the dependent node will score on resolved parents only
        visiting.add(nid)
        for link in nodes[nid].parents:
            visit(link.parent_id)
        visiting.discard(nid)
        if nid not in scored:
            _score_node(nodes[nid], scored)
            scored[nid] = nodes[nid].score if nodes[nid].score is not None else 0.0
            order.append(nid)

    for nid in list(nodes):
        visit(nid)
    return nodes


def band(score: Optional[float]) -> str:
    if score is None:
        return "abstain"
    if score >= _BAND_GREEN:
        return "green"
    if score >= _BAND_AMBER:
        return "amber"
    return "red"


def to_graph(nodes: dict[str, ClaimNode], *, source: str = "", answer: str = "",
             question: str = "", sources: Optional[list] = None) -> dict:
    """Convert a scored claim tree into the {nodes, edges, stats} shape the renderer consumes.

    Optional roots build the left spine: ``question`` → ``answer`` → base claims (anchored + orphan)
    → derived children. Edge kinds: ``asks`` (question → answer), ``decomposes`` (answer/question →
    base claim), ``derives`` (parent → child, labelled 'entails' for a load-bearing premise else
    'supports'), and ``sibling`` (a vertical AND / OR connector between the parents that JOINTLY gate
    the same child — co-gating siblings only)."""
    gnodes = []
    if question:
        gnodes.append({
            "id": "__question__", "type": "question", "kind": "question", "orphan": False,
            "label": question, "full": question, "score": None, "band": "abstain",
        })
    if answer:
        gnodes.append({
            "id": "__answer__", "type": "answer", "kind": "answer", "orphan": False,
            "label": answer, "full": answer, "score": None, "band": "abstain",
        })
    for n in nodes.values():
        gnodes.append({
            "id": n.id, "type": n.kind, "label": (n.text[:60] + "…") if len(n.text) > 60 else n.text,
            "full": n.text, "kind": n.kind, "score": n.score, "band": band(n.score),
            "groundedness": n.groundedness, "source_attribution": n.source_attribution,
            "source_quality": n.source_quality, "own_truthfulness": n.own_truthfulness,
            "reasoning_fidelity": n.reasoning_fidelity, "parent_min": n.parent_min,
            "relevance": n.relevance, "branch": n.branch, "note": n.note,
            "threshold": AXIOM_THRESHOLD, "orphan": n.kind == "orphan",
        })
    # corpus: source-document nodes (the claims ground against these)
    for s in (sources or []):
        sid = str(s.get("id") or s.get("title") or "src")
        gnodes.append({
            "id": "src:" + sid, "type": "source", "kind": "source", "orphan": False,
            "label": s.get("title") or s.get("domain") or sid, "full": s.get("quote") or s.get("text") or "",
            "domain": s.get("domain"), "support": s.get("support"),
            "fetch_success": s.get("fetch_success", s.get("fetchSuccess", True)),
            "score": None, "band": "abstain",
        })
    gedges = []
    if question and answer:
        gedges.append({"source": "__question__", "target": "__answer__", "kind": "asks",
                       "relation": "asks", "load_bearing": False, "label": "answered by"})
    stem_root = "__answer__" if answer else ("__question__" if question else None)
    if stem_root:
        for n in nodes.values():
            if n.kind in ("anchored", "orphan"):
                gedges.append({"source": stem_root, "target": n.id, "kind": "decomposes",
                               "relation": "stem", "load_bearing": False, "label": ""})
    for n in nodes.values():
        for link in n.parents:
            gedges.append({
                "source": link.parent_id, "target": n.id, "kind": "derives",
                "relation": "or" if link.or_group else "and",
                "load_bearing": link.load_bearing, "or_group": link.or_group,
                "label": link.relation or ("entails" if link.load_bearing else "supports"),
            })
    # grounds edges: a claim that actually grounded points to the source that entailed it
    src_ids = {n["id"] for n in gnodes if n["type"] == "source"}
    grounded_srcs: set = set()
    for n in nodes.values():
        sid = "src:" + str(n.grounded_source) if n.grounded_source else None
        if sid in src_ids and (n.groundedness or 0) >= 0.5:
            gedges.append({"source": n.id, "target": sid, "kind": "grounds",
                           "relation": "grounds", "load_bearing": False, "label": "grounds in"})
            grounded_srcs.add(sid)
    # a source no claim grounds to (or a failed fetch) is an orphan
    for gn in gnodes:
        if gn["type"] != "source":
            continue
        if not gn.get("fetch_success"):
            gn["orphan"], gn["orphan_reason"] = True, "source could not be retrieved"
        elif gn["id"] not in grounded_srcs:
            gn["orphan"], gn["orphan_reason"] = True, "source grounds no claim in this answer"
    _layout(gnodes, gedges, has_answer=bool(answer), has_question=bool(question))
    gedges.extend(_sibling_edges(nodes, gnodes))       # vertical AND/OR after positions are known
    stats = {
        "nodes": len(gnodes), "edges": len(gedges),
        "anchored": sum(1 for n in nodes.values() if n.kind == "anchored"),
        "derived": sum(1 for n in nodes.values() if n.kind == "derived"),
        "orphans": sum(1 for n in nodes.values() if n.kind == "orphan"),
        "bands": {b: sum(1 for n in nodes.values() if band(n.score) == b)
                  for b in ("green", "amber", "red", "abstain")},
    }
    return {"source": source, "question": question, "answer": answer, "nodes": gnodes,
            "edges": gedges, "stats": stats, "axiom_threshold": AXIOM_THRESHOLD}


def _sibling_edges(nodes: dict[str, ClaimNode], gnodes: list[dict]) -> list[dict]:
    """Vertical AND/OR connectors between parents that JOINTLY gate the same child. Load-bearing
    non-OR parents form the AND cluster; each ``or_group`` is an OR cluster. Only members sharing a
    column are connected (consecutive by y). Half-siblings (parents of different children, or non-
    load-bearing) get no link."""
    pos = {n["id"]: n for n in gnodes}
    out: list[dict] = []
    seen: set = set()
    for child in nodes.values():
        loose: list[str] = []
        groups: dict[str, list[str]] = {}
        for link in child.parents:
            if not link.load_bearing or link.parent_id not in pos:
                continue
            if link.or_group:
                groups.setdefault(link.or_group, []).append(link.parent_id)
            else:
                loose.append(link.parent_id)
        clusters = [("and", loose)] + [("or", ids) for ids in groups.values()]
        for rel, ids in clusters:
            bycol: dict[float, list[str]] = {}
            for i in ids:
                bycol.setdefault(pos[i]["x"], []).append(i)
            for col_ids in bycol.values():
                if len(col_ids) < 2:
                    continue
                col_ids.sort(key=lambda i: pos[i]["y"])
                for a, b in zip(col_ids, col_ids[1:]):
                    key = (a, b, rel)
                    if key in seen:
                        continue
                    seen.add(key)
                    out.append({"source": a, "target": b, "kind": "sibling",
                                "relation": rel, "child": child.id})
    return out


# --- DAG layout: question → answer → base claims (anchored/orphan) → derived children ----------
_COL_W, _ROW_H = 300, 116


def _layout(gnodes: list[dict], gedges: list[dict], *, has_answer: bool = False,
            has_question: bool = False) -> None:
    """Column by longest DERIVE depth (base claims = 0), shifted right by the left-spine roots
    (question, answer). To read like a tree, each derived child is centered on the mean y of its
    load-bearing parents (then de-overlapped within its column); the answer/question sit leftmost,
    centered on the base column."""
    parents_of: dict[str, list[str]] = {n["id"]: [] for n in gnodes}
    for e in gedges:
        if e["kind"] == "derives" and e["target"] in parents_of:
            parents_of[e["target"]].append(e["source"])
    depth: dict[str, int] = {}

    def d(nid: str, seen: frozenset = frozenset()) -> int:
        if nid in depth:
            return depth[nid]
        if nid in seen:                       # cycle guard
            return 0
        ps = parents_of.get(nid, [])
        val = 0 if not ps else 1 + max(d(p, seen | {nid}) for p in ps)
        depth[nid] = val
        return val

    claim_nodes = [n for n in gnodes if n["type"] not in ("answer", "question", "source")]
    for n in claim_nodes:
        d(n["id"])
    off = (1 if has_question else 0) + (1 if has_answer else 0)
    pos = {n["id"]: n for n in gnodes}
    by_layer: dict[int, list[dict]] = {}
    for n in claim_nodes:
        by_layer.setdefault(depth[n["id"]], []).append(n)
    maxd = max(by_layer) if by_layer else 0

    # base column (depth 0): non-orphans first, then orphans, stacked evenly
    base = by_layer.get(0, [])
    base.sort(key=lambda n: (1 if n.get("orphan") else 0, n["id"]))
    for i, n in enumerate(base):
        n["x"], n["y"] = 80 + off * _COL_W, 60 + i * _ROW_H

    # deeper columns: center each child on the mean y of its load-bearing parents, de-overlap by y
    for layer in range(1, maxd + 1):
        grp = by_layer.get(layer, [])
        for n in grp:
            ys = [pos[p]["y"] for p in parents_of.get(n["id"], []) if p in pos and "y" in pos[p]]
            n["_want"] = sum(ys) / len(ys) if ys else 60.0
        grp.sort(key=lambda n: (n["_want"], n["id"]))
        y = -1e9
        for n in grp:
            yy = max(n["_want"], y + _ROW_H)
            n["x"], n["y"], y = 80 + (off + layer) * _COL_W, yy, yy
        for n in grp:
            n.pop("_want", None)

    cy = (sum(n["y"] for n in base) / len(base)) if base else \
         (sum(n["y"] for n in claim_nodes) / len(claim_nodes) if claim_nodes else 60)
    if has_answer:
        for n in gnodes:
            if n["type"] == "answer":
                n["x"], n["y"] = 80 + (1 if has_question else 0) * _COL_W, cy
    if has_question:
        for n in gnodes:
            if n["type"] == "question":
                n["x"], n["y"] = 80, cy

    # corpus column: source docs to the right of the deepest claim column (non-orphan first)
    srcs = [n for n in gnodes if n["type"] == "source"]
    if srcs:
        srcs.sort(key=lambda n: (1 if n.get("orphan") else 0, n["id"]))
        sx = 80 + (off + maxd + 1) * _COL_W
        for i, n in enumerate(srcs):
            n["x"], n["y"] = sx, 60 + i * _ROW_H


def demo_claim_tree() -> dict[str, ClaimNode]:
    """A deterministic finance-flavored claim tree that exercises EVERY scoring branch.

    Mirrors the offline-fixtures spirit: no model, hand-built so the graph lands on visibly different
    node scores (weakest-link red, max-above-axiom green, min-below-axiom amber, OR-group, orphan)."""
    nodes = [
        # anchored leaves (source-grounded)
        ClaimNode(id="a_rev", text="Q3 revenue was $4.2B", kind="anchored",
                  groundedness=0.95, source_attribution=0.92, source_quality=0.88),
        ClaimNode(id="a_margin", text="Cloud gross margin improved YoY", kind="anchored",
                  groundedness=0.90, source_attribution=0.85, source_quality=0.80),
        # weakest-link demo: strong grounding but a low-quality source drags min to 0.40
        ClaimNode(id="a_inquiry", text="A regulatory inquiry opened in August", kind="anchored",
                  groundedness=0.88, source_attribution=0.90, source_quality=0.40),
        # unsupported demo: everything low
        ClaimNode(id="a_cov", text="Coverage volume rose 18%", kind="anchored",
                  groundedness=0.30, source_attribution=0.30, source_quality=0.35),
        # derived — above axiom -> max(own, reasoning) lifts it
        ClaimNode(id="d_growth", text="Cloud is the primary growth driver", kind="derived",
                  groundedness=0.60, source_attribution=0.60, source_quality=0.62, reasoning_fidelity=0.90,
                  parents=[ParentLink("a_rev"), ParentLink("a_margin")]),
        # derived — below axiom (weak inquiry premise) -> min(own, reasoning) holds it back
        ClaimNode(id="d_risk", text="The issuer's risk profile materially increased", kind="derived",
                  groundedness=0.65, source_attribution=0.65, source_quality=0.68, reasoning_fidelity=0.92,
                  parents=[ParentLink("a_inquiry")]),
        # derived — OR-group (inquiry OR coverage) + a strong AND parent (growth), still below axiom
        ClaimNode(id="d_outlook", text="Near-term outlook carries elevated risk", kind="derived",
                  groundedness=0.70, source_attribution=0.72, source_quality=0.75, reasoning_fidelity=0.80,
                  parents=[ParentLink("d_growth"),
                           ParentLink("a_inquiry", or_group="signal"),
                           ParentLink("a_cov", or_group="signal")]),
        # orphan — floating fact, no anchor/parents/reasoning -> relevance stub only
        ClaimNode(id="o_ceo", text="The CEO previously worked at a competitor", kind="orphan", relevance=0.35),
    ]
    return score_tree({n.id: n for n in nodes})


def render_html(graph: dict, title: str = "Claim Tree — nodal scoring") -> str:
    """Render a ``to_graph`` payload as a single self-contained HTML doc: DAG canvas (pan/zoom),
    band-colored nodes, AND (solid) / OR (dashed) support edges, and a click-to-open panel showing
    every sub-score and which rule fired."""
    import json as _json

    data = _json.dumps(graph).replace("</", "<\\/")
    esc = (title or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return _TREE_HTML.replace("__TITLE__", esc).replace("__PAYLOAD__", data)


_TREE_HTML = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>__TITLE__</title><style>
 :root{--bg:#0b0f1a;--bg2:#0f1420;--panel:#141b2b;--line:#28324e;--txt:#eef2fb;--mut:#8b97b5;
   --green:#22c55e;--amber:#eab308;--red:#ef4444;--abstain:#64748b;--q:#a78bfa;--a:#60a5fa;}
 *{box-sizing:border-box}html,body{margin:0;height:100%;font:14px/1.45 "Segoe UI",system-ui,Roboto,sans-serif;
   background:radial-gradient(1200px 800px at 30% -10%,#16203a 0%,var(--bg) 60%);color:var(--txt)}
 #app{display:flex;height:100vh}
 #main{flex:1;position:relative;overflow:hidden}
 #bar{position:absolute;left:16px;top:12px;z-index:5;font-weight:700;font-size:15px;letter-spacing:.02em;
   text-shadow:0 1px 6px rgba(0,0,0,.6)}
 #bar small{display:block;font-weight:500;font-size:11px;color:var(--mut);margin-top:2px;max-width:520px}
 #panel{width:340px;flex:0 0 340px;background:linear-gradient(180deg,#161d2e,#121826);border-left:1px solid var(--line);
   padding:18px;overflow:auto;box-shadow:-8px 0 30px rgba(0,0,0,.35)}
 #panel h2{font-size:14px;margin:0 0 6px;line-height:1.35}#panel .k{color:var(--mut);font-size:12px}
 .row{display:flex;justify-content:space-between;align-items:center;padding:6px 0;border-bottom:1px dashed var(--line);font-size:12px}
 .row b{font-weight:700}.pill{display:inline-block;padding:2px 10px;border-radius:999px;font-size:11px;font-weight:700}
 .bar{height:8px;border-radius:5px;background:#0b1120;overflow:hidden;margin:3px 0 4px}.bar>span{display:block;height:100%;border-radius:5px}
 #hint{position:absolute;left:16px;bottom:12px;color:var(--mut);font-size:11px}
 #legend{position:absolute;right:16px;top:12px;font-size:11px;color:var(--mut);background:rgba(11,16,28,.72);
   backdrop-filter:blur(6px);padding:10px 12px;border-radius:10px;border:1px solid var(--line);box-shadow:0 8px 24px rgba(0,0,0,.4)}
 #legend .r{display:flex;align-items:center;gap:7px;padding:2px 0}#legend .sw{width:18px;height:11px;border-radius:3px}
 svg{width:100%;height:100%;cursor:grab}svg.drag{cursor:grabbing}
 .node{cursor:pointer}.node text{fill:var(--txt);pointer-events:none}
 .ttl{font-size:12.5px;font-weight:600}.hdr{font-size:10px;font-weight:800;letter-spacing:.1em}
 .m{font-size:10px;fill:var(--mut)}.sc{font-size:13px;font-weight:800}
</style></head><body><div id="app">
 <div id="main">
   <svg id="svg"><defs>
     <filter id="sh" x="-40%" y="-40%" width="180%" height="180%"><feDropShadow dx="0" dy="3" stdDeviation="4" flood-color="#000" flood-opacity="0.55"/></filter>
     <linearGradient id="grad-green" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#22c55e" stop-opacity=".30"/><stop offset="1" stop-color="#22c55e" stop-opacity=".05"/></linearGradient>
     <linearGradient id="grad-amber" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#eab308" stop-opacity=".30"/><stop offset="1" stop-color="#eab308" stop-opacity=".05"/></linearGradient>
     <linearGradient id="grad-red" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ef4444" stop-opacity=".30"/><stop offset="1" stop-color="#ef4444" stop-opacity=".05"/></linearGradient>
     <linearGradient id="grad-abstain" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#64748b" stop-opacity=".30"/><stop offset="1" stop-color="#64748b" stop-opacity=".05"/></linearGradient>
     <linearGradient id="grad-question" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#a78bfa" stop-opacity=".34"/><stop offset="1" stop-color="#a78bfa" stop-opacity=".06"/></linearGradient>
     <linearGradient id="grad-answer" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#60a5fa" stop-opacity=".34"/><stop offset="1" stop-color="#60a5fa" stop-opacity=".06"/></linearGradient>
     <linearGradient id="grad-source" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#10b981" stop-opacity=".30"/><stop offset="1" stop-color="#10b981" stop-opacity=".05"/></linearGradient>
   </defs><g id="view"></g></svg>
   <div id="bar">__TITLE__<small id="sub"></small></div>
   <div id="legend"></div>
   <div id="hint">scroll = zoom · drag = pan · click a node for its scoring</div></div>
 <div id="panel"><div class="k">Select a node</div><h2 id="ptitle">Claim tree</h2>
   <div class="k" id="thr"></div><div id="detail" style="margin-top:12px"></div></div>
</div><script>
const G=__PAYLOAD__, NS="http://www.w3.org/2000/svg", NW=252, NH=96;
const BAND={green:"#22c55e",amber:"#eab308",red:"#ef4444",abstain:"#64748b"};
const ACC={question:"#a78bfa",answer:"#60a5fa"};
const $=id=>document.getElementById(id);
function el(t,a){const e=document.createElementNS(NS,t);for(const k in(a||{}))e.setAttribute(k,a[k]);return e;}
const pct=v=>v==null?"—":Math.round(v*100)+"%";
$("sub").textContent=(G.question?("Q: "+G.question):"")||(G.source?("source: "+G.source):"");
$("thr").textContent="axiom threshold = "+pct(G.axiom_threshold)+" (all load-bearing parents)";
$("legend").innerHTML=["green","amber","red","abstain"].map(b=>`<div class="r"><span class="sw" style="background:${BAND[b]}"></span>${b}</div>`).join("")
  +`<div class="r" style="margin-top:5px"><span class="sw" style="border-top:2px solid #7c93c9;height:0"></span>entails / supports</div>`
  +`<div class="r"><span class="sw" style="border-top:2px solid #93a3c9;height:0"></span>AND (sibling)</div>`
  +`<div class="r"><span class="sw" style="border-top:2px dashed #eab308;height:0"></span>OR (alternative)</div>`
  +`<div class="r" style="margin-top:5px"><span class="sw" style="background:#10b981"></span>source doc (corpus)</div>`
  +`<div class="r"><span class="sw" style="border-top:2px solid #10b981;height:0"></span>grounds in</div>`;
// wrap text into up to `lines` lines of ~max chars, ellipsis on overflow (never spills the box)
function wrapN(s,max,lines){s=(s||"").trim();const w=s.split(/\s+/);const L=[""];
  for(const x of w){const i=L.length-1;
    if(((L[i]?L[i]+" ":"")+x).length<=max)L[i]=(L[i]?L[i]+" ":"")+x;
    else if(L.length<lines)L.push(x);
    else{L[i]=L[i].slice(0,Math.max(0,max-1))+"…";return L;}}
  return L;}
function chip(x,y,txt,color){const g=el("g",{});const w=txt.length*5.7+12;
  g.appendChild(el("rect",{x:x-w/2,y:y-8.5,width:w,height:16,rx:8,ry:8,fill:"#0b1120",stroke:"#28324e","stroke-width":1}));
  const t=el("text",{x:x,y:y+3,"text-anchor":"middle","font-size":9.5,"font-weight":700,fill:color||"#aeb8d0"});t.textContent=txt;g.appendChild(t);return g;}
function drawBar(v){const c=v==null?BAND.abstain:(v>=0.75?BAND.green:v>=0.5?BAND.amber:BAND.red);
  return `<div class="bar"><span style="width:${Math.round((v||0)*100)}%;background:${c}"></span></div>`;}
function detail(n){
  if(n.kind==="question"||n.kind==="answer"){
    $("ptitle").textContent=n.kind==="question"?"Question":"Answer";
    $("detail").innerHTML=`<div style="font-size:13px;line-height:1.5">${(n.full||"").replace(/</g,"&lt;")}</div>
      <div class="k" style="margin-top:12px">${n.kind==="question"?"Answered by the model; the answer decomposes into the base claims.":"Decomposes into the base claims (anchored + orphan) to the right."}</div>`;return;}
  if(n.kind==="source"){
    $("ptitle").textContent="Source document";
    $("detail").innerHTML=`<h2>${(n.label||"").replace(/</g,"&lt;")}</h2>
      <div class="row"><span>domain</span><b>${n.domain||"—"}</b></div>
      <div class="row"><span>support</span><b>${n.support||"n/a"}</b></div>
      <div class="row"><span>fetched</span><b>${n.fetch_success?"yes":"no"}</b></div>
      ${n.full?`<div class="k" style="margin-top:10px">“${(n.full||"").replace(/</g,"&lt;")}”</div>`:""}
      ${n.orphan?`<div class="k" style="margin-top:10px;color:#ef4444">orphan — ${n.orphan_reason||""}</div>`:`<div class="k" style="margin-top:10px;color:#10b981">grounds one or more claims</div>`}`;return;}
  $("ptitle").textContent="Claim scoring";
  const rows=[];
  const sub=(k,v)=>v==null?"":`<div class="row"><span>${k}</span><b>${pct(v)}</b></div>${drawBar(v)}`;
  rows.push(`<h2>${(n.full||n.label).replace(/</g,"&lt;")}</h2>`);
  rows.push(`<div style="margin:6px 0 12px"><span class="pill" style="background:${BAND[n.band]}22;color:${BAND[n.band]}">${n.kind} · ${n.band}</span>
     <span style="float:right;font-weight:800;font-size:20px;color:${BAND[n.band]}">${pct(n.score)}</span></div>`);
  if(n.kind!=="orphan"){
    rows.push(`<div class="k" style="margin-bottom:2px">truthfulness sub-scores</div>`);
    rows.push(sub("groundedness",n.groundedness));
    rows.push(sub("source attribution",n.source_attribution));
    rows.push(sub("source quality",n.source_quality));
    rows.push(`<div class="row"><span>min(truthfulness) = weakest of 3</span><b>${pct(n.own_truthfulness)}</b></div>`);
  }
  if(n.kind==="derived"){
    rows.push(`<div class="k" style="margin:12px 0 2px">logic</div>`);
    rows.push(sub("logical completeness",n.reasoning_fidelity));
    rows.push(`<div class="row"><span>load-bearing parents min (m)</span><b>${pct(n.parent_min)}</b></div>`);
    const ax=n.parent_min!=null&&n.parent_min>=G.axiom_threshold;
    rows.push(`<div class="k" style="margin-top:6px;color:${ax?'#22c55e':'#eab308'}">${ax
      ?"m ≥ "+pct(G.axiom_threshold)+" → score = max(logical completeness, min truthfulness)"
      :"m < "+pct(G.axiom_threshold)+" → logical completeness INVALID → score = min(truthfulness)"}</div>`);
  }
  if(n.kind==="orphan"){rows.push(sub("relevance (stub)",n.relevance));}
  rows.push(`<div class="k" style="margin:14px 0 2px">rule applied</div><div style="font-size:12px">${n.branch}</div>`);
  if(n.note)rows.push(`<div class="k" style="margin-top:8px">${n.note}</div>`);
  $("detail").innerHTML=rows.join("");
}
function drawEdge(view,e,a,b){
  const x1=a.x+NW,y1=a.y+NH/2,x2=b.x,y2=b.y+NH/2,mx=(x1+x2)/2;
  const derive=e.kind==="derives",spine=e.kind==="decomposes"||e.kind==="asks",grounds=e.kind==="grounds";
  const col=grounds?"#10b981":(derive?(e.relation==="or"?"#eab308":"#7c93c9"):"#465579");
  const dash=spine?"3 4":(derive&&e.relation==="or"?"7 5":"");
  view.appendChild(el("path",{d:`M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}`,fill:"none",
    stroke:col,opacity:grounds?0.85:(derive?0.92:0.5),"stroke-linecap":"round",
    "stroke-width":grounds?2:(derive?(e.load_bearing?2.3:1.5):1.3),"stroke-dasharray":dash}));
  if(e.label)view.appendChild(chip(mx,(y1+y2)/2,e.label,grounds?"#7ff0c4":(derive?"#c3ccff":"#93a0bd")));
}
function drawNode(view,n){
  const g=el("g",{class:"node",transform:`translate(${n.x},${n.y})`});
  if(n.type==="question"||n.type==="answer"){
    const acc=ACC[n.type];
    g.appendChild(el("rect",{width:NW,height:NH,rx:15,ry:15,fill:`url(#grad-${n.type})`,stroke:acc,"stroke-width":2,filter:"url(#sh)"}));
    const h=el("text",{x:15,y:22,class:"hdr",fill:acc});h.textContent=n.type.toUpperCase();g.appendChild(h);
    wrapN(n.full||n.label,36,3).forEach((ln,i)=>{const t=el("text",{x:15,y:40+i*15,"font-size":11});t.textContent=ln;g.appendChild(t);});
    g.addEventListener("click",()=>detail(n));view.appendChild(g);return;
  }
  if(n.type==="source"){
    const acc="#10b981";
    g.appendChild(el("rect",{width:NW,height:NH,rx:15,ry:15,fill:"url(#grad-source)",
      stroke:n.orphan?"#ef4444":acc,"stroke-width":2,"stroke-dasharray":n.orphan?"6 5":"",filter:"url(#sh)"}));
    const h=el("text",{x:15,y:22,class:"hdr",fill:n.orphan?"#ef4444":acc});h.textContent="SOURCE";g.appendChild(h);
    wrapN(n.label,32,2).forEach((ln,i)=>{const t=el("text",{x:15,y:42+i*16,class:"ttl"});t.textContent=ln;g.appendChild(t);});
    const m=el("text",{x:15,y:NH-10,class:"m"});m.textContent=(n.domain||"")+" · "+(n.support||"n/a")+(n.orphan?" · orphan":"");g.appendChild(m);
    g.addEventListener("click",()=>detail(n));view.appendChild(g);return;
  }
  const c=BAND[n.band]||BAND.abstain;
  g.appendChild(el("rect",{width:NW,height:NH,rx:15,ry:15,fill:`url(#grad-${n.band})`,
    stroke:n.orphan?"#ef4444":c,"stroke-width":2,"stroke-dasharray":n.orphan?"6 5":"",filter:"url(#sh)"}));
  g.appendChild(el("rect",{x:0,y:0,width:5,height:NH,rx:2,ry:2,fill:c}));   // accent spine
  wrapN(n.label,30,2).forEach((ln,i)=>{const t=el("text",{x:16,y:26+i*17,class:"ttl"});t.textContent=ln;g.appendChild(t);});
  const meta=el("text",{x:16,y:70,class:"m"});
  meta.textContent=n.kind+(n.kind==="derived"?` · m=${pct(n.parent_min)}`:(n.kind==="orphan"?" · relevance stub":" · min(3)"));g.appendChild(meta);
  const s=el("text",{x:NW-14,y:86,"text-anchor":"end",class:"sc",fill:c});s.textContent=pct(n.score)+" · "+n.band;g.appendChild(s);
  g.addEventListener("click",()=>detail(n));view.appendChild(g);
}
function drawSibling(view,a,b,rel){        // vertical bracket in the gutter, drawn ON TOP, linking the boxes
  const col=a.x,gx=col-24,y1=a.y+NH/2,y2=b.y+NH/2,my=(y1+y2)/2;
  const c=rel==="or"?"#eab308":"#93a3c9",dash=rel==="or"?"5 4":"";
  const st={fill:"none",stroke:c,"stroke-width":1.7,"stroke-linecap":"round","stroke-dasharray":dash};
  view.appendChild(el("path",{d:`M${gx},${y1} L${gx},${y2}`,...st}));
  view.appendChild(el("path",{d:`M${gx},${y1} L${col},${y1}`,...st}));
  view.appendChild(el("path",{d:`M${gx},${y2} L${col},${y2}`,...st}));
  view.appendChild(chip(gx,my,rel.toUpperCase(),c));
}
function draw(){
  const view=$("view");view.innerHTML="";const pos={};G.nodes.forEach(n=>pos[n.id]=n);
  G.edges.forEach(e=>{if(e.kind==="sibling")return;const a=pos[e.source],b=pos[e.target];if(a&&b)drawEdge(view,e,a,b);});
  G.nodes.forEach(n=>drawNode(view,n));
  G.edges.forEach(e=>{if(e.kind!=="sibling")return;const a=pos[e.source],b=pos[e.target];if(a&&b)drawSibling(view,a,b,e.relation);});
  fit();
}
let vx=0,vy=0,vs=1;const apply=()=>$("view").setAttribute("transform",`translate(${vx},${vy}) scale(${vs})`);
function fit(){const xs=G.nodes.map(n=>n.x),ys=G.nodes.map(n=>n.y);if(!xs.length)return;
  const w=$("main").clientWidth,h=$("main").clientHeight;
  const maxx=Math.max(...xs)+NW+50,maxy=Math.max(...ys)+NH+50,minx=Math.min(...xs)-50,miny=Math.min(...ys)-30;
  vs=Math.min(1,Math.min(w/(maxx-minx),h/(maxy-miny)));vx=-minx*vs+10;vy=-miny*vs+10;apply();}
const svg=$("svg");
svg.addEventListener("wheel",e=>{e.preventDefault();const f=e.deltaY<0?1.1:0.9;const r=svg.getBoundingClientRect();
  const mx=e.clientX-r.left,my=e.clientY-r.top;vx=mx-(mx-vx)*f;vy=my-(my-vy)*f;vs*=f;apply();},{passive:false});
let dn=false,px,py;svg.addEventListener("mousedown",e=>{dn=true;px=e.clientX;py=e.clientY;svg.classList.add("drag");});
addEventListener("mouseup",()=>{dn=false;svg.classList.remove("drag");});
addEventListener("mousemove",e=>{if(!dn)return;vx+=e.clientX-px;vy+=e.clientY-py;px=e.clientX;py=e.clientY;apply();});
draw();
if(G.nodes.length)detail(G.nodes.find(n=>n.kind==="derived")||G.nodes.find(n=>n.kind!=="answer"&&n.kind!=="question")||G.nodes[0]);
</script></body></html>"""
