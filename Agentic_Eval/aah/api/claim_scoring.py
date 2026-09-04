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


def to_graph(nodes: dict[str, ClaimNode], *, source: str = "", answer: str = "") -> dict:
    """Convert a scored claim tree into the {nodes, edges, stats} shape the renderer consumes.

    ``answer`` (optional) adds a leftmost ANSWER node that the base claims (anchored + orphan) stem
    from. Edge kinds: ``decomposes`` (answer → base claim), ``derives`` (parent → child, labelled
    'entails' for a load-bearing premise else 'supports'), and ``sibling`` (a vertical AND / OR
    connector between the parents that JOINTLY gate the same child — co-gating siblings only)."""
    gnodes = []
    if answer:
        gnodes.append({
            "id": "__answer__", "type": "answer", "kind": "answer", "orphan": False,
            "label": (answer[:90] + "…") if len(answer) > 90 else answer, "full": answer,
            "score": None, "band": "abstain",
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
    gedges = []
    if answer:
        for n in nodes.values():
            if n.kind in ("anchored", "orphan"):
                gedges.append({"source": "__answer__", "target": n.id, "kind": "decomposes",
                               "relation": "stem", "load_bearing": False, "label": ""})
    for n in nodes.values():
        for link in n.parents:
            gedges.append({
                "source": link.parent_id, "target": n.id, "kind": "derives",
                "relation": "or" if link.or_group else "and",
                "load_bearing": link.load_bearing, "or_group": link.or_group,
                "label": link.relation or ("entails" if link.load_bearing else "supports"),
            })
    _layout(gnodes, gedges, has_answer=bool(answer))
    gedges.extend(_sibling_edges(nodes, gnodes))       # vertical AND/OR after positions are known
    stats = {
        "nodes": len(gnodes), "edges": len(gedges),
        "anchored": sum(1 for n in nodes.values() if n.kind == "anchored"),
        "derived": sum(1 for n in nodes.values() if n.kind == "derived"),
        "orphans": sum(1 for n in nodes.values() if n.kind == "orphan"),
        "bands": {b: sum(1 for n in nodes.values() if band(n.score) == b)
                  for b in ("green", "amber", "red", "abstain")},
    }
    return {"source": source, "answer": answer, "nodes": gnodes, "edges": gedges, "stats": stats,
            "axiom_threshold": AXIOM_THRESHOLD}


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


# --- DAG layout: answer → base claims (anchored/orphan) → derived children ----------
_COL_W, _ROW_H = 300, 104


def _layout(gnodes: list[dict], gedges: list[dict], *, has_answer: bool = False) -> None:
    """Column by longest DERIVE depth (base claims=0), shifted right by one when an answer node is
    present. The answer sits leftmost, vertically centered on the base column."""
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

    claim_nodes = [n for n in gnodes if n["type"] != "answer"]
    for n in claim_nodes:
        d(n["id"])
    off = 1 if has_answer else 0
    by_layer: dict[int, list[dict]] = {}
    for n in claim_nodes:
        by_layer.setdefault(depth[n["id"]], []).append(n)
    for layer, group in by_layer.items():
        group.sort(key=lambda n: (0 if not n.get("orphan") else 1, n["id"]))
        for i, n in enumerate(group):
            n["x"] = 80 + (layer + off) * _COL_W
            n["y"] = 60 + i * _ROW_H
    if has_answer:
        base = by_layer.get(0, [])
        ay = (sum(n["y"] for n in base) / len(base)) if base else 60
        for n in gnodes:
            if n["type"] == "answer":
                n["x"], n["y"] = 80, ay


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
 :root{--bg:#0f1420;--panel:#161d2e;--line:#2a3350;--txt:#e6ebf5;--mut:#8b97b5;
   --green:#22c55e;--amber:#eab308;--red:#ef4444;--abstain:#64748b;}
 *{box-sizing:border-box}html,body{margin:0;height:100%;font:14px/1.4 system-ui,Segoe UI,Roboto,sans-serif;background:var(--bg);color:var(--txt)}
 #app{display:flex;height:100vh}#main{flex:1;position:relative;overflow:hidden}
 #panel{width:320px;flex:0 0 320px;background:var(--panel);border-left:1px solid var(--line);padding:16px;overflow:auto}
 #panel h2{font-size:14px;margin:0 0 2px}#panel .k{color:var(--mut);font-size:12px}
 .row{display:flex;justify-content:space-between;padding:5px 0;border-bottom:1px dashed var(--line);font-size:12px}
 .row b{font-weight:600}.pill{display:inline-block;padding:1px 8px;border-radius:999px;font-size:11px;font-weight:700}
 .bar{height:7px;border-radius:4px;background:#0d1322;overflow:hidden;margin-top:3px}.bar>span{display:block;height:100%}
 #hint{position:absolute;left:12px;bottom:10px;color:var(--mut);font-size:11px}
 #legend{position:absolute;left:12px;top:10px;font-size:11px;color:var(--mut);background:rgba(11,16,28,.7);padding:8px 10px;border-radius:8px;border:1px solid var(--line)}
 #legend .r{display:flex;align-items:center;gap:6px;padding:1px 0}#legend .sw{width:16px;height:10px;border-radius:3px}
 svg{width:100%;height:100%;cursor:grab}svg.drag{cursor:grabbing}
 .node{cursor:pointer}.node text{fill:var(--txt);pointer-events:none}.node .s{font-size:11px;font-weight:700}
 .node .m{font-size:10px;fill:var(--mut)}
</style></head><body><div id="app">
 <div id="main"><svg id="svg"><g id="view"></g></svg>
   <div id="legend"></div>
   <div id="hint">scroll = zoom · drag = pan · click a node for its scoring</div></div>
 <div id="panel"><div class="k">Select a node</div><h2>__TITLE__</h2>
   <div class="k" id="thr"></div><div id="detail" style="margin-top:12px"></div></div>
</div><script>
const G=__PAYLOAD__, NS="http://www.w3.org/2000/svg", NW=232, NH=66;
const BAND={green:"#22c55e",amber:"#eab308",red:"#ef4444",abstain:"#64748b"};
const $=id=>document.getElementById(id);
function el(t,a){const e=document.createElementNS(NS,t);for(const k in(a||{}))e.setAttribute(k,a[k]);return e;}
const pct=v=>v==null?"—":Math.round(v*100)+"%";
$("thr").textContent="axiom threshold = "+pct(G.axiom_threshold)+" (load-bearing parents)";
$("legend").innerHTML=["green","amber","red","abstain"].map(b=>`<div class="r"><span class="sw" style="background:${BAND[b]}"></span>${b}</div>`).join("")
  +`<div class="r" style="margin-top:4px"><span class="sw" style="border-top:2px solid #94a3b8;height:0"></span>AND (load-bearing)</div>`
  +`<div class="r"><span class="sw" style="border-top:2px dashed #94a3b8;height:0"></span>OR (alternative)</div>`;
function drawBar(v){const c=v==null?BAND.abstain:(v>=0.75?BAND.green:v>=0.5?BAND.amber:BAND.red);
  return `<div class="bar"><span style="width:${Math.round((v||0)*100)}%;background:${c}"></span></div>`;}
function detail(n){
  if(n.kind==="answer"){$("detail").innerHTML=`<h2>Answer</h2><div style="font-size:13px">${(n.full||"").replace(/</g,"&lt;")}</div>
    <div class="k" style="margin-top:10px">The answer decomposes into the base claims (anchored + orphan) to its right.</div>`;return;}
  const rows=[];
  const sub=(k,v)=>v==null?"":`<div class="row"><span>${k}</span><b>${pct(v)}</b></div>${drawBar(v)}`;
  rows.push(`<h2>${(n.full||n.label).replace(/</g,"&lt;")}</h2>`);
  rows.push(`<div style="margin:6px 0 10px"><span class="pill" style="background:${BAND[n.band]}22;color:${BAND[n.band]}">${n.kind} · ${n.band}</span>
     <span style="float:right;font-weight:700;font-size:18px">${pct(n.score)}</span></div>`);
  if(n.kind!=="orphan"){
    rows.push(`<div class="k" style="margin-bottom:2px">truthfulness sub-scores</div>`);
    rows.push(sub("groundedness",n.groundedness));
    rows.push(sub("source attribution",n.source_attribution));
    rows.push(sub("source quality",n.source_quality));
    rows.push(`<div class="row"><span>own truthfulness = min(3)</span><b>${pct(n.own_truthfulness)}</b></div>`);
  }
  if(n.kind==="derived"){
    rows.push(`<div class="k" style="margin:10px 0 2px">logic</div>`);
    rows.push(sub("logical completeness",n.reasoning_fidelity));
    rows.push(`<div class="row"><span>load-bearing parents min (m)</span><b>${pct(n.parent_min)}</b></div>`);
    const ax=n.parent_min!=null&&n.parent_min>=G.axiom_threshold;
    rows.push(`<div class="k" style="margin-top:6px">${ax
      ?"m ≥ "+pct(G.axiom_threshold)+" → score = max(logical completeness, min truthfulness)"
      :"m < "+pct(G.axiom_threshold)+" → logical completeness INVALID → score = min(truthfulness)"}</div>`);
  }
  if(n.kind==="orphan"){rows.push(sub("relevance (stub)",n.relevance));}
  rows.push(`<div class="k" style="margin:12px 0 2px">rule applied</div><div style="font-size:12px">${n.branch}</div>`);
  if(n.note)rows.push(`<div class="k" style="margin-top:8px">${n.note}</div>`);
  $("detail").innerHTML=rows.join("");
}
function elabel(x,y,txt,anchor){const t=el("text",{x:x,y:y,"text-anchor":anchor||"middle","font-size":10,fill:"#aeb8d0"});t.textContent=txt;return t;}
function draw(){
  const view=$("view");view.innerHTML="";const pos={};G.nodes.forEach(n=>pos[n.id]=n);
  G.edges.forEach(e=>{const a=pos[e.source],b=pos[e.target];if(!a||!b)return;
    if(e.kind==="sibling"){                       // vertical AND/OR connector just left of the column
      const x=a.x-16,y1=a.y+NH/2,y2=b.y+NH/2;
      view.appendChild(el("path",{d:`M${x},${y1} L${x},${y2}`,fill:"none",stroke:"#8b97b5",
        "stroke-width":1.4,"stroke-dasharray":e.relation==="or"?"5 4":""}));
      view.appendChild(elabel(x-5,(y1+y2)/2+3,e.relation.toUpperCase(),"end"));
      return;
    }
    const x1=a.x+NW,y1=a.y+NH/2,x2=b.x,y2=b.y+NH/2,mx=(x1+x2)/2;
    const decomp=e.kind==="decomposes";
    view.appendChild(el("path",{d:`M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}`,fill:"none",
      stroke:decomp?"#5a6785":"#94a3b8",opacity:decomp?0.55:(e.load_bearing?0.9:0.5),
      "stroke-width":decomp?1.2:(e.load_bearing?2:1.3),
      "stroke-dasharray":decomp?"2 3":(e.relation==="or"?"6 4":"")}));
    if(e.label)view.appendChild(elabel(mx,(y1+y2)/2-4,e.label));
  });
  G.nodes.forEach(n=>{
    if(n.type==="answer"){
      const g=el("g",{class:"node",transform:`translate(${n.x},${n.y})`});
      g.appendChild(el("rect",{width:NW,height:NH,rx:10,ry:10,fill:"#3b82f61f",stroke:"#3b82f6","stroke-width":2}));
      const h=el("text",{x:12,y:20,class:"m"});h.textContent="ANSWER";g.appendChild(h);
      const t=el("text",{x:12,y:42});t.textContent=n.label.length>34?n.label.slice(0,33)+"…":n.label;g.appendChild(t);
      g.addEventListener("click",()=>detail(n));view.appendChild(g);return;
    }
    const c=BAND[n.band]||BAND.abstain;
    const g=el("g",{class:"node",transform:`translate(${n.x},${n.y})`});
    g.appendChild(el("rect",{width:NW,height:NH,rx:10,ry:10,fill:c+"1f",
      stroke:n.orphan?"#ef4444":c,"stroke-width":2,"stroke-dasharray":n.orphan?"5 3":""}));
    const t=el("text",{x:12,y:22});t.textContent=n.label;g.appendChild(t);
    const m=el("text",{x:12,y:40,class:"m"});m.textContent=n.kind+(n.kind==="derived"?` · m=${pct(n.parent_min)}`:"");g.appendChild(m);
    const s=el("text",{x:12,y:56,class:"s",fill:c});s.textContent=pct(n.score)+" "+n.band+(n.kind==="anchored"?" · min(3)":"");g.appendChild(s);
    g.addEventListener("click",()=>detail(n));view.appendChild(g);});
  fit();
}
let vx=0,vy=0,vs=1;const apply=()=>$("view").setAttribute("transform",`translate(${vx},${vy}) scale(${vs})`);
function fit(){const xs=G.nodes.map(n=>n.x),ys=G.nodes.map(n=>n.y);if(!xs.length)return;
  const w=$("main").clientWidth,h=$("main").clientHeight;
  const maxx=Math.max(...xs)+NW+40,maxy=Math.max(...ys)+NH+40,minx=Math.min(...xs)-20,miny=Math.min(...ys)-20;
  vs=Math.min(1,Math.min(w/(maxx-minx),h/(maxy-miny)));vx=-minx*vs+10;vy=-miny*vs+10;apply();}
const svg=$("svg");
svg.addEventListener("wheel",e=>{e.preventDefault();const f=e.deltaY<0?1.1:0.9;const r=svg.getBoundingClientRect();
  const mx=e.clientX-r.left,my=e.clientY-r.top;vx=mx-(mx-vx)*f;vy=my-(my-vy)*f;vs*=f;apply();},{passive:false});
let dn=false,px,py;svg.addEventListener("mousedown",e=>{dn=true;px=e.clientX;py=e.clientY;svg.classList.add("drag");});
addEventListener("mouseup",()=>{dn=false;svg.classList.remove("drag");});
addEventListener("mousemove",e=>{if(!dn)return;vx+=e.clientX-px;vy+=e.clientY-py;px=e.clientX;py=e.clientY;apply();});
draw();if(G.nodes.length)detail(G.nodes.find(n=>n.kind!=="anchored")||G.nodes[0]);
</script></body></html>"""
