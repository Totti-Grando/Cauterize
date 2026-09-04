"""Complete claim TREE with the corpus in play — the polished renderer, real DeBERTa scoring.

question -> answer -> base claims (anchored + orphan) -> derived children, PLUS the source docs
(corpus) each anchored claim grounds against. No requirements column. All grounding is the live
local DeBERTa NLI over hybrid retrieval.

Run:  .venv/Scripts/python.exe scripts/diag_tree_complete.py
"""
import os, sys, asyncio, webbrowser

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ["AAH_NLI_MODEL"] = os.path.abspath(os.path.join("models", "deberta-mnli-fever-anli"))
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ.setdefault("AAH_NLI_DEVICE", "cuda")

from aah.api import claim_scoring as cs
from aah.api.claim_extraction import ExtractedClaim, ClaimParent, build_claim_nodes_retrieval

QUESTION = "What were Acme Corp's Q3 2024 financial results and outlook?"
ANSWER = ("Acme's Q3 2024 revenue was $4.2 billion, up 12% year over year. The cloud division grew 40% "
          "and now makes up 35% of revenue, so cloud is the primary growth driver. Net income reached "
          "$1.5 billion and operating margin expanded to 45%. The CEO seemed very optimistic.")
SOURCES = [
  {"id": "filing", "title": "Q3 2024 10-Q", "domain": "sec.gov", "support": "strong", "fetch_success": True,
   "text": "Acme Corp reported Q3 2024 revenue of $4.2 billion, up 12% year over year. Operating margin expanded to 30%. Net income was $900 million."},
  {"id": "pr", "title": "Q3 press release", "domain": "acme.com", "support": "strong", "fetch_success": True,
   "text": "Acme's cloud division grew 40% in Q3 2024 and now represents 35% of total revenue. The company repurchased $1 billion of stock."},
  {"id": "analyst", "title": "Analyst note", "domain": "analysts.com", "support": "weak", "fetch_success": True,
   "text": "Analysts noted Acme faces rising competition in cloud infrastructure."},
  {"id": "portal", "title": "Investor portal (paywalled)", "domain": "acme.com", "support": "not_evaluable", "fetch_success": False, "text": ""},
]
EVIDENCE = [
  {"title": "Q3 2024 10-Q", "quote": "revenue of $4.2 billion, up 12%, net income was $900 million, operating margin 30%", "support": "strong", "domain": "sec.gov"},
  {"title": "Q3 press release", "quote": "cloud division grew 40% and now represents 35% of total revenue", "support": "strong", "domain": "acme.com"},
]
CLAIMS = [
  ExtractedClaim("c0", "Acme Q3 2024 revenue was $4.2 billion, up 12% year over year", "anchored"),
  ExtractedClaim("c1", "Acme's cloud division grew 40% in Q3 2024", "anchored"),
  ExtractedClaim("c2", "the cloud division now makes up 35% of total revenue", "anchored"),
  ExtractedClaim("c3", "Acme Q3 2024 net income reached $1.5 billion", "anchored"),            # FALSE (filing: $900M)
  ExtractedClaim("c4", "operating margin expanded to 45%", "anchored"),                         # FALSE (filing: 30%)
  ExtractedClaim("c5", "cloud is the primary growth driver", "derived",
                 [ClaimParent("c1"), ClaimParent("c2")], ["cloud grew 40%", "cloud is 35% of revenue"]),
  ExtractedClaim("c6", "The CEO seemed very optimistic", "orphan"),
]


async def main():
    tree = await build_claim_nodes_retrieval(CLAIMS, question=QUESTION, sources=SOURCES,
                                             evidence=EVIDENCE, k=8, tau=0.5)
    graph = cs.to_graph(tree, source="acme-q3-2024 (real DeBERTa)", question=QUESTION,
                        answer=ANSWER, sources=SOURCES)
    out = os.path.abspath("claim_tree_complete.html")
    open(out, "w", encoding="utf-8").write(cs.render_html(graph, title="Claim Tree — complete (corpus + scoring)"))

    print(f"{'id':4} {'type':8} {'score':>6} {'ground':>7} grounded_source")
    for cid in ("c0", "c1", "c2", "c3", "c4", "c5", "c6"):
        n = tree[cid]
        sc = "  -  " if n.score is None else f"{n.score:.2f}"
        gr = "  -  " if n.groundedness is None else f"{n.groundedness:.3f}"
        print(f"{cid:4} {n.kind:8} {sc:>6} {gr:>7} {n.grounded_source}")
    kinds = {}
    for e in graph["edges"]:
        kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
    src = [n for n in graph["nodes"] if n["type"] == "source"]
    print("edge kinds:", kinds)
    print("sources:", [(n["label"], "orphan" if n.get("orphan") else "grounds") for n in src])
    print("wrote", out)
    webbrowser.open("file:///" + out.replace(os.sep, "/"))


asyncio.run(main())
