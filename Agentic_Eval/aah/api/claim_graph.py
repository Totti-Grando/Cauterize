"""Claim-graph builder: turn evaluation records into a nodes/edges graph for visualization.

This is a PURE, deterministic transform with NO engine coupling and NO model calls. It reads
the UI ``evaluation`` dict produced by :func:`aah.api.ui_adapter.audit_to_evaluation` — the same
shape for offline fixtures and live runs alike — and emits an explicit claim graph:

    question ──has──▶ requirement ──decomposes──▶ check/claim ──grounds──▶ source
                                        │
                                        └──scored_in──▶ dimension
    check/claim ──gates──▶ question         (must-pass / critical / gating-subtype = an AND gate)

Node types
    question    the task the model answered (one root per evaluation)
    requirement an analyst-level requirement the task decomposes into
    claim       a born-tagged factual/grounding check (an assertion to be entailed by a source)
    check       any other atomic yes/no check (correctness, completeness, format, ...)
    source      a piece of retrieved evidence a claim can be grounded in
    dimension   a scoring dimension (carries tier + gating)

Special cases made first-class (this is the point of the graph)
    orphan      a node with no meaningful relationship — an unsupported/abstaining claim with no
                source, a check under no requirement, or a source that grounds nothing / failed to
                fetch. Orphans are flagged (``orphan``/``orphan_reason``) and laid out in their own
                band so they are impossible to miss.
    AND relation a must-pass / critical / gating-subtype check: it alone can gate the whole run to
                FAIL. Rendered as a hard "gates" edge; its parent requirement is an AND group.
    SOFT relation ordinary sibling checks that are uniformly averaged within a dimension (no single
                one vetoes) — the "or-ish" soft aggregation. Marked ``relation="soft"``.

The builder is intentionally tolerant: every field is read with ``.get`` and missing pieces simply
produce a thinner graph rather than an error, so a partial or legacy record still renders.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

# A check is a grounding *claim* (an assertion to be entailed by a source) when its dimension sits in
# the Evidence & Truthfulness or RAG-Quality taxonomy category. The evaluation dict carries each
# check's ``category`` straight from the run config (ui_adapter reads aah/config/taxonomy.py), so this
# classification is CONFIG-DRIVEN, not a frozen name list.
_GROUNDING_CATEGORIES = frozenset({"evidence_truthfulness", "rag_quality"})
# Fallback for legacy records that predate the ``category`` field — the 8 grounding dimensions as of
# taxonomy v1. Only consulted when a check carries no category.
_GROUNDING_DIMS_FALLBACK = frozenset({
    "factual_consistency", "source_fabrication", "source_quality", "source_attribution",
    "retrieval_precision", "retrieval_recall", "context_utilization", "context_relevance",
})


def _is_grounding(check: dict) -> bool:
    """Is this check a grounding claim? Driven by the taxonomy ``category`` carried in the record;
    falls back to the legacy dimension-name set only when no category is present."""
    cat = check.get("category")
    if cat:
        return cat in _GROUNDING_CATEGORIES
    return (check.get("dimension") or "") in _GROUNDING_DIMS_FALLBACK

# Support levels (from evidence records) that count as a real grounding anchor. A source with
# any other level (or a failed fetch) can never receive a grounds-edge, so it may orphan.
_SUPPORTING = frozenset({"strong", "partial"})

# Layout lanes: x-column per node type (left→right follows the decomposition).
_LAYER = {"question": 0, "requirement": 1, "claim": 2, "check": 2, "source": 3, "dimension": 4}
_COL_W = 260
_ROW_H = 96
_ORPHAN_GAP = 60          # vertical gap before the orphan band within a column
_CAT_GAP = 40             # vertical gap between taxonomy-category bands in the dimension column


def _state(score: Any) -> str:
    """pass / fail / abstain from a check's numeric score (None or missing => abstain)."""
    if score is None:
        return "abstain"
    try:
        return "pass" if float(score) >= 0.999 else "fail"
    except (TypeError, ValueError):
        return "abstain"


def _is_gate(check: dict, gating_dims: set[str]) -> bool:
    """A check is an AND gate if it is must-pass, its failure subtype gates its (scored) dimension,
    it sits in a CRITICAL/gating dimension, or its tier is critical. Any one of these can veto the
    whole run (spec §7.4 / taxonomy §1 gating subtypes / aggregator)."""
    if check.get("must_pass"):
        return True
    if check.get("subtype_gates"):                       # scored dim vetoing on this failure subtype
        return True
    if (check.get("tier") or "").lower() == "critical":
        return True
    return check.get("dimension") in gating_dims


def _short(text: str, n: int = 90) -> str:
    text = (text or "").strip().replace("\n", " ")
    return text if len(text) <= n else text[: n - 1] + "…"


def build_evaluation_graph(ev: dict, prefix: str = "") -> dict:
    """Build one evaluation's claim graph: {evaluationId, question, verdict, nodes, edges, stats}.

    ``prefix`` namespaces node ids so several evaluations can share one canvas without collisions.
    """
    ev_id = str(ev.get("id") or ev.get("questionId") or "E")
    p = f"{prefix}{ev_id}:"
    nodes: list[dict] = []
    edges: list[dict] = []
    seen: set[str] = set()

    def add_node(node_id: str, **attrs) -> str:
        if node_id not in seen:
            seen.add(node_id)
            nodes.append({"id": node_id, **attrs})
        return node_id

    def add_edge(src: str, dst: str, kind: str, **attrs) -> None:
        edges.append({"source": src, "target": dst, "kind": kind, **attrs})

    # Which dimensions gate (from the per-dimension breakdown), so a check inherits its dim's gate.
    per_dim = {d.get("dimension"): d for d in ev.get("perDimension", []) if d.get("dimension")}
    gating_dims = {dim for dim, d in per_dim.items()
                   if d.get("gating") or (d.get("tier") or "").lower() == "critical"}

    # --- root: the question ---------------------------------------------------------
    q_node = add_node(
        p + "q", type="question", label=_short(ev.get("question") or ev_id, 70),
        full=ev.get("question") or "", verdict=ev.get("verdict"),
        overall=ev.get("overall"), gated_by=ev.get("gatedBy"),
        provider=ev.get("provider"), category=ev.get("category"),
    )

    # --- source nodes (evidence) ----------------------------------------------------
    grounded_source_ids: set[str] = set()
    for e in ev.get("evidence", []) or []:
        add_node(
            p + "src:" + str(e.get("id") or e.get("title") or len(nodes)),
            type="source", label=_short(e.get("title") or e.get("domain") or "source", 44),
            domain=e.get("domain"), support=e.get("support"),
            fetch_success=e.get("fetchSuccess", e.get("fetch_success", True)),
            quote=_short(e.get("quote") or "", 160),
            url=e.get("canonicalUrl") or e.get("sourceUrl") or "",
        )

    supporting_sources = [
        n for n in nodes
        if n["type"] == "source" and n.get("fetch_success") and (n.get("support") in _SUPPORTING)
    ]

    # --- dimension lane: EVERY configured dimension (the run's full per-dimension breakdown), so the
    # graph reflects the complete evaluation configuration — not only dimensions a check happened to
    # touch. Dimensions no check scores simply carry no scored_in edge (``exercised=False``). --------
    for d in ev.get("perDimension", []) or []:
        dname = d.get("dimension")
        if not dname:
            continue
        add_node(
            p + "dim:" + dname, type="dimension", label=dname.replace("_", " "),
            dimension=dname, category=d.get("category"), tier=d.get("tier"),
            gating=dname in gating_dims, score=d.get("score"), weight=d.get("weight"),
        )

    # --- requirements → checks/claims ----------------------------------------------
    for gi, group in enumerate(ev.get("rubric", []) or []):
        req_text = (group.get("requirement") or "").strip()
        req_orphan = (not req_text) or req_text == "(unspecified requirement)"
        req_id = add_node(
            p + f"r{gi}", type="requirement",
            label=_short(req_text or "(unspecified requirement)", 60),
            full=req_text, orphan=req_orphan,
            orphan_reason="check has no parent requirement" if req_orphan else "",
        )
        if not req_orphan:
            add_edge(q_node, req_id, "has")

        for check in group.get("checks", []) or []:
            dim = check.get("dimension") or ""
            is_claim = _is_grounding(check)
            state = _state(check.get("score"))
            gate = _is_gate(check, gating_dims)
            cid = add_node(
                p + "c:" + str(check.get("id") or f"{gi}-{len(nodes)}"),
                type="claim" if is_claim else "check",
                label=_short(check.get("text") or check.get("id") or "check", 60),
                full=check.get("text") or "", dimension=dim, category=check.get("category"),
                subtype=check.get("subtype"), tier=check.get("tier"),
                eval_method=check.get("eval_method"), must_pass=bool(check.get("must_pass")),
                subtype_gates=bool(check.get("subtype_gates")),
                state=state, reason=_short(check.get("reason") or "", 200),
                attack_success=check.get("attack_success"), gate=gate,
            )
            # decomposition edge: AND (hard gate) vs soft (uniformly-averaged sibling)
            add_edge(req_id, cid, "decomposes", relation="and" if gate else "soft")
            # gate edge straight to the root so a vetoing check is visually unmissable
            if gate:
                add_edge(cid, q_node, "gates", relation="and", failed=(state == "fail"))
            # scored-in edge to the dimension lane
            if dim:
                did = add_node(
                    p + "dim:" + dim, type="dimension", label=dim.replace("_", " "),
                    dimension=dim, category=(per_dim.get(dim) or {}).get("category"),
                    tier=(per_dim.get(dim) or {}).get("tier"),
                    gating=dim in gating_dims,
                    score=(per_dim.get(dim) or {}).get("score"),
                    weight=(per_dim.get(dim) or {}).get("weight"),
                )
                add_edge(cid, did, "scored_in")
            # grounding: a passing claim links to its supporting sources; a failing/abstaining
            # claim (or one with no source available) is an ORPHAN — an unsupported claim.
            if is_claim:
                if state == "pass" and supporting_sources:
                    for s in supporting_sources:
                        add_edge(cid, s["id"], "grounds", support=s.get("support"))
                        grounded_source_ids.add(s["id"])
                else:
                    node = _get(nodes, cid)
                    node["orphan"] = True
                    node["orphan_reason"] = (
                        "unsupported claim — not entailed by any source" if state == "fail"
                        else "claim not verifiable against a source" if state == "abstain"
                        else "no source available to ground this claim"
                    )

    # --- orphan sources: fetched-but-unused, failed fetch, or non-supporting -------
    for n in nodes:
        if n["type"] != "source":
            continue
        if not n.get("fetch_success"):
            n["orphan"], n["orphan_reason"] = True, "source could not be retrieved"
        elif n["id"] not in grounded_source_ids:
            reason = ("source not usable as evidence (support: %s)" % (n.get("support") or "n/a")
                      if n.get("support") not in _SUPPORTING
                      else "source grounds no claim in this answer")
            n["orphan"], n["orphan_reason"] = True, reason

    # mark which configured dimensions an actual check scored (the rest are configured-but-untouched)
    scored_dims = {e["target"] for e in edges if e["kind"] == "scored_in"}
    for n in nodes:
        if n["type"] == "dimension":
            n["exercised"] = n["id"] in scored_dims

    _layout(nodes)
    stats = _stats(nodes, edges)
    return {
        "evaluationId": ev_id, "question": ev.get("question"), "verdict": ev.get("verdict"),
        "provider": ev.get("provider"), "gatedBy": ev.get("gatedBy"),
        "nodes": nodes, "edges": edges, "stats": stats,
    }


def build_graph(evaluations: Iterable[dict], *, source: str = "") -> dict:
    """Build the full claim-graph payload for a list of evaluations.

    Returns ``{source, summary, graphs:[per-evaluation graph, ...]}``. Each per-evaluation graph is
    independently laid out, so a viewer can show one at a time (recommended) or an overview.
    """
    graphs = [build_evaluation_graph(ev) for ev in (evaluations or [])]
    summary = {
        "evaluations": len(graphs),
        "nodes": sum(g["stats"]["nodes"] for g in graphs),
        "edges": sum(g["stats"]["edges"] for g in graphs),
        "orphans": sum(g["stats"]["orphans"] for g in graphs),
        "gates": sum(g["stats"]["gates"] for g in graphs),
        "verdicts": _tally(g.get("verdict") for g in graphs),
    }
    return {"source": source, "summary": summary, "graphs": graphs}


# --- internals ----------------------------------------------------------------------
def _index(nodes: list[dict], node_id: str) -> int:
    for i, n in enumerate(nodes):
        if n["id"] == node_id:
            return i
    return -1


def _get(nodes: list[dict], node_id: str) -> dict:
    return nodes[_index(nodes, node_id)]


def _layout(nodes: list[dict]) -> None:
    """Assign (x, y) by type-column. Orphan nodes are pushed into a lower band per column; dimension
    nodes are ordered and banded by their taxonomy category (a gap between category groups) so the
    dimension lane reads as the grouped evaluation configuration."""
    by_layer: dict[int, list[dict]] = {}
    for n in nodes:
        by_layer.setdefault(_LAYER.get(n["type"], 2), []).append(n)
    for layer, group in by_layer.items():
        # non-orphans first (stable), then a gap, then orphans; dimensions additionally group by
        # category (other node types keep their original id ordering — empty category key).
        group.sort(key=lambda n: (bool(n.get("orphan")),
                                  (n.get("category") or "~") if n["type"] == "dimension" else "",
                                  n["id"]))
        x = 80 + layer * _COL_W
        y = 60
        prev_orphan = False
        prev_cat: Optional[str] = None
        for n in group:
            if n.get("orphan") and not prev_orphan:
                y += _ORPHAN_GAP        # visual break between main nodes and the orphan band
                prev_orphan = True
            if n["type"] == "dimension":
                cat = n.get("category") or "~"
                if prev_cat is not None and cat != prev_cat:
                    y += _CAT_GAP       # visual break between taxonomy-category bands
                prev_cat = cat
            n["x"], n["y"] = x, y
            y += _ROW_H


def _stats(nodes: list[dict], edges: list[dict]) -> dict:
    by_type: dict[str, int] = {}
    for n in nodes:
        by_type[n["type"]] = by_type.get(n["type"], 0) + 1
    return {
        "nodes": len(nodes), "edges": len(edges),
        "by_type": by_type,
        "orphans": sum(1 for n in nodes if n.get("orphan")),
        "gates": sum(1 for n in nodes if n.get("gate")),
        "and_edges": sum(1 for e in edges if e.get("relation") == "and"),
        "soft_edges": sum(1 for e in edges if e.get("relation") == "soft"),
        "claims": by_type.get("claim", 0),
        "sources": by_type.get("source", 0),
    }


def _tally(values: Iterable[Optional[str]]) -> dict:
    out: dict[str, int] = {}
    for v in values:
        if v:
            out[v] = out.get(v, 0) + 1
    return out


# --- standalone HTML renderer -------------------------------------------------------
def render_html(payload: dict, title: str = "Claim Graph") -> str:
    """Render a ``build_graph`` payload into a single self-contained HTML document.

    No external assets, no build step, no keys: embeds the graph JSON and a small vanilla-JS SVG
    renderer with an evaluation switcher, pan/zoom, tooltips, and a legend. Orphans render with a
    dashed red outline and sit in their own band; AND/gate edges are bold red; soft (averaged)
    edges are thin grey; grounding edges green. Open the file in any browser.
    """
    import json as _json

    data = _json.dumps(payload).replace("</", "<\\/")
    tmpl = _HTML_TEMPLATE.replace("__TITLE__", _escape(title))
    return tmpl.replace("__PAYLOAD__", data)


def _escape(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


_HTML_TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>__TITLE__</title>
<style>
  :root{--bg:#0f1420;--panel:#161d2e;--line:#2a3350;--txt:#e6ebf5;--mut:#8b97b5;}
  *{box-sizing:border-box} html,body{margin:0;height:100%;font:14px/1.4 system-ui,Segoe UI,Roboto,sans-serif;background:var(--bg);color:var(--txt)}
  #app{display:flex;height:100vh}
  #side{width:290px;flex:0 0 290px;background:var(--panel);border-right:1px solid var(--line);padding:16px;overflow:auto}
  #side h1{font-size:16px;margin:0 0 4px} #side .sub{color:var(--mut);font-size:12px;margin-bottom:14px}
  .stat{display:flex;justify-content:space-between;padding:3px 0;border-bottom:1px dashed var(--line);font-size:12px}
  .stat b{font-weight:600}
  .sel{width:100%;margin:12px 0;padding:8px;background:#0d1322;color:var(--txt);border:1px solid var(--line);border-radius:8px}
  .leg{margin-top:14px} .leg h3{font-size:12px;color:var(--mut);text-transform:uppercase;letter-spacing:.06em;margin:14px 0 6px}
  .leg .row{display:flex;align-items:center;gap:8px;padding:3px 0;font-size:12px}
  .sw{width:22px;height:14px;border-radius:4px;flex:0 0 22px} .ln{width:22px;height:0;flex:0 0 22px}
  #main{flex:1;position:relative;overflow:hidden}
  #hint{position:absolute;left:12px;bottom:10px;color:var(--mut);font-size:11px;z-index:5}
  #tip{position:absolute;pointer-events:none;background:#0b101c;border:1px solid var(--line);border-radius:8px;
       padding:8px 10px;max-width:320px;font-size:12px;display:none;z-index:10;box-shadow:0 8px 30px rgba(0,0,0,.5)}
  #tip .t{font-weight:600;margin-bottom:4px} #tip .k{color:var(--mut)}
  svg{width:100%;height:100%;cursor:grab} svg.drag{cursor:grabbing}
  .node rect{stroke-width:1.5} .node text{fill:var(--txt);pointer-events:none}
  .node .lbl{font-size:12px} .node .meta{font-size:10px;fill:var(--mut)}
  .orphan rect{stroke-dasharray:5 3}
  text.badge{font-size:9px;font-weight:700}
</style></head>
<body><div id="app">
  <div id="side">
    <h1>__TITLE__</h1>
    <div class="sub" id="src"></div>
    <div id="summary"></div>
    <select class="sel" id="pick"></select>
    <label style="display:flex;align-items:center;gap:8px;font-size:12px;margin:2px 0 10px;cursor:pointer">
      <input type="checkbox" id="showIdle"/> show idle dimensions</label>
    <div id="estats"></div>
    <div class="leg" id="legend"></div>
  </div>
  <div id="main">
    <svg id="svg"><g id="view"></g></svg>
    <div id="tip"></div>
    <div id="hint">scroll = zoom · drag = pan · hover a node for detail</div>
  </div>
</div>
<script>
const PAYLOAD = __PAYLOAD__;
let SHOW_IDLE=false, CUR=0;                 // hide unexercised dimensions by default
const NS="http://www.w3.org/2000/svg", NW=210, NH=62;
const TYPE={question:"#3b82f6",requirement:"#8b5cf6",claim:"#0ea5e9",check:"#64748b",source:"#10b981",dimension:"#f59e0b"};
const STATE={pass:"#22c55e",fail:"#ef4444",abstain:"#eab308"};
const EDGE={has:"#64748b",decomposes:"#94a3b8",grounds:"#10b981",scored_in:"#3b82f6",gates:"#ef4444"};
const $=id=>document.getElementById(id);
function el(t,a){const e=document.createElementNS(NS,t);for(const k in(a||{}))e.setAttribute(k,a[k]);return e;}

function renderSummary(){
  const s=PAYLOAD.summary||{};
  $("src").textContent="source: "+(PAYLOAD.source||"—");
  const rows=[["evaluations",s.evaluations],["nodes",s.nodes],["edges",s.edges],
    ["orphans",s.orphans],["AND gates",s.gates]];
  $("summary").innerHTML=rows.map(r=>`<div class="stat"><span>${r[0]}</span><b>${r[1]??0}</b></div>`).join("");
  const v=s.verdicts||{};
  $("summary").innerHTML+=Object.keys(v).map(k=>`<div class="stat"><span>verdict: ${k}</span><b>${v[k]}</b></div>`).join("");
}
function renderLegend(){
  const nt=Object.entries(TYPE).map(([k,c])=>`<div class="row"><span class="sw" style="background:${c}"></span>${k}</div>`).join("");
  const ed=[["gates / AND","#ef4444",3],["decomposes","#94a3b8",1.5],["grounds","#10b981",2],["scored_in","#3b82f6",1]]
    .map(([k,c,w])=>`<div class="row"><span class="ln" style="border-top:${w}px solid ${c}"></span>${k}</div>`).join("");
  const st=Object.entries(STATE).map(([k,c])=>`<div class="row"><span class="sw" style="background:${c};width:12px;height:12px;border-radius:50%"></span>${k}</div>`).join("");
  $("legend").innerHTML=`<h3>node type</h3>${nt}<h3>relationship</h3>${ed}
    <h3>check state</h3>${st}<h3>special</h3>
    <div class="row"><span class="sw" style="background:transparent;border:1.5px dashed #ef4444"></span>orphan (no relationship)</div>
    <div class="row"><span class="sw" style="background:transparent;border:1.5px solid #f59e0b"></span>gate (can veto run)</div>`;
}
function tip(html,x,y){const t=$("tip");if(!html){t.style.display="none";return;}t.innerHTML=html;t.style.display="block";
  t.style.left=Math.min(x+14,innerWidth-340)+"px";t.style.top=(y+14)+"px";}

function draw(g){
  const view=$("view"); view.innerHTML="";
  // visibility: hide unexercised dimension nodes unless the toggle is on
  const vis=g.nodes.filter(n=>SHOW_IDLE||!(n.type==="dimension"&&n.exercised===false));
  // recompute the dimension column y among visible dims — compact but keep the category bands
  const Y={}; vis.forEach(n=>Y[n.id]=n.y);
  const dims=vis.filter(n=>n.type==="dimension").sort((a,b)=>a.y-b.y);
  {let y=60,pc=null;dims.forEach(n=>{const c=n.category||"~";if(pc!==null&&c!==pc)y+=40;pc=c;Y[n.id]=y;y+=96;});}
  const pos={}; vis.forEach(n=>pos[n.id]={x:n.x,y:Y[n.id]});
  // edges first (skip any whose endpoint is hidden)
  g.edges.forEach(e=>{
    const a=pos[e.source],b=pos[e.target]; if(!a||!b)return;
    const x1=a.x+NW,y1=a.y+NH/2,x2=b.x,y2=b.y+NH/2;
    const mx=(x1+x2)/2;
    const p=el("path",{d:`M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}`,
      fill:"none",stroke:EDGE[e.kind]||"#64748b",
      "stroke-width":e.kind==="gates"?2.6:(e.relation==="and"?2.2:1.3),
      "stroke-dasharray":e.kind==="scored_in"?"4 4":(e.kind==="grounds"?"":""),
      opacity:e.kind==="scored_in"?0.5:0.85});
    view.appendChild(p);
  });
  // nodes
  vis.forEach(n=>{
    const grp=el("g",{class:"node"+(n.orphan?" orphan":""),transform:`translate(${n.x},${Y[n.id]})`});
    const fill=TYPE[n.type]||"#334155";
    const r=el("rect",{width:NW,height:NH,rx:10,ry:10,fill:fill+"22",
      stroke:n.orphan?"#ef4444":(n.gate?"#f59e0b":fill),"stroke-width":n.gate?2.4:1.5});
    grp.appendChild(r);
    const label=el("text",{x:12,y:22,class:"lbl"}); label.textContent=n.label||n.id; grp.appendChild(label);
    const meta=el("text",{x:12,y:40,class:"meta"});
    meta.textContent=(n.type==="claim"||n.type==="check")?((n.dimension||"")+" · "+(n.tier||"")):
      (n.type==="source"?("support: "+(n.support||"n/a")):(n.type==="dimension"?((n.category?n.category+" · ":"")+"tier: "+(n.tier||"?")+(n.exercised===false?" · idle":"")):n.type));
    grp.appendChild(meta);
    // state dot
    if(n.state){grp.appendChild(el("circle",{cx:NW-14,cy:16,r:5,fill:STATE[n.state]||"#64748b"}));}
    if(n.gate){const bg=el("text",{x:NW-40,y:NH-8,class:"badge",fill:"#f59e0b"});bg.textContent="GATE";grp.appendChild(bg);}
    if(n.orphan){const bo=el("text",{x:12,y:NH-8,class:"badge",fill:"#ef4444"});bo.textContent="ORPHAN";grp.appendChild(bo);}
    grp.addEventListener("mousemove",ev=>{
      let h=`<div class="t">${(n.full||n.label||"").replace(/</g,"&lt;")}</div>`;
      h+=`<div class="k">type: ${n.type}${n.dimension?" · "+n.dimension:""}${n.category?" · "+n.category:""}</div>`;
      if(n.state)h+=`<div>state: <b>${n.state}</b>${n.must_pass?" · must-pass":""}</div>`;
      if(n.reason)h+=`<div class="k">${n.reason.replace(/</g,"&lt;")}</div>`;
      if(n.support!=null)h+=`<div>support: ${n.support} · fetched: ${n.fetch_success}</div>`;
      if(n.quote)h+=`<div class="k">“${n.quote.replace(/</g,"&lt;")}”</div>`;
      if(n.orphan)h+=`<div style="color:#ef4444">orphan — ${n.orphan_reason||""}</div>`;
      if(n.gate)h+=`<div style="color:#f59e0b">gate — ${n.subtype_gates?("vetoes on subtype: "+(n.subtype||"?")):"can veto the whole run"}</div>`;
      tip(h,ev.clientX,ev.clientY);
    });
    grp.addEventListener("mouseleave",()=>tip(null));
    view.appendChild(grp);
  });
  fit(vis,Y);
}
let vx=0,vy=0,vs=1;
function apply(){$("view").setAttribute("transform",`translate(${vx},${vy}) scale(${vs})`);}
function fit(vis,Y){
  const xs=vis.map(n=>n.x),ys=vis.map(n=>Y[n.id]);
  if(!xs.length){vx=0;vy=0;vs=1;apply();return;}
  const w=$("main").clientWidth,h=$("main").clientHeight;
  const maxx=Math.max(...xs)+NW+40,maxy=Math.max(...ys)+NH+40,minx=Math.min(...xs)-20,miny=Math.min(...ys)-20;
  vs=Math.min(1,Math.min(w/(maxx-minx),h/(maxy-miny)));vx=-minx*vs+10;vy=-miny*vs+10;apply();
}
function pick(i){CUR=i;draw(PAYLOAD.graphs[i]);
  const g=PAYLOAD.graphs[i],s=g.stats;
  $("estats").innerHTML=`<div class="stat"><span>verdict</span><b>${g.verdict||"—"}</b></div>`+
    (g.gatedBy?`<div class="stat"><span>gated by</span><b>${g.gatedBy}</b></div>`:"")+
    `<div class="stat"><span>claims</span><b>${s.claims}</b></div>`+
    `<div class="stat"><span>sources</span><b>${s.sources}</b></div>`+
    `<div class="stat"><span>orphans</span><b style="color:${s.orphans?'#ef4444':'inherit'}">${s.orphans}</b></div>`+
    `<div class="stat"><span>gates (AND)</span><b>${s.gates}</b></div>`;
}
function init(){
  renderSummary();renderLegend();
  const sel=$("pick");
  PAYLOAD.graphs.forEach((g,i)=>{const o=document.createElement("option");o.value=i;
    o.textContent=`${g.evaluationId} — ${g.verdict||"?"}${g.stats.orphans?"  ⚠"+g.stats.orphans+" orphan":""}`;sel.appendChild(o);});
  sel.addEventListener("change",e=>pick(+e.target.value));
  $("showIdle").checked=SHOW_IDLE;
  $("showIdle").addEventListener("change",e=>{SHOW_IDLE=e.target.checked;pick(CUR);});
  const svg=$("svg");
  svg.addEventListener("wheel",e=>{e.preventDefault();const f=e.deltaY<0?1.1:0.9;
    const r=svg.getBoundingClientRect(),mx=e.clientX-r.left,my=e.clientY-r.top;
    vx=mx-(mx-vx)*f;vy=my-(my-vy)*f;vs*=f;apply();},{passive:false});
  let dn=false,px,py;
  svg.addEventListener("mousedown",e=>{dn=true;px=e.clientX;py=e.clientY;svg.classList.add("drag");});
  addEventListener("mouseup",()=>{dn=false;svg.classList.remove("drag");});
  addEventListener("mousemove",e=>{if(!dn)return;vx+=e.clientX-px;vy+=e.clientY-py;px=e.clientX;py=e.clientY;apply();});
  if(PAYLOAD.graphs.length)pick(0);
}
init();
</script></body></html>"""
