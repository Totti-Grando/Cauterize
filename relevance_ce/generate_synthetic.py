"""
Synthetic minimal-pair generator (v2) for the 9-class claim-question relevance cross-encoder.

Each question gets DIRECT claim(s) plus perturbations that each break exactly one dimension.
All entities, people and regulators are fictional. Output: JSONL, one row per pair, grouped by qid,
split by anchor entity (no entity appears in more than one split).

    python generate_synthetic.py --n_questions 12000 --out data/synthetic.jsonl --seed 7

Coverage (v2):
  question types   point-in-time attribute | trend over a range ("since 2022", "between 2021 and 2024")
                   | relation (acquired, sued, sub-advisor, CEO appointment, regulatory fine)
  entities         asset managers, banks, dealers, insurers, people, regulators; tickers (ALIAS tag);
                   homonyms (two firms sharing a stem -> bare stem is UNRESOLVED)
  periods          quarter / half / year, written several ways ("Q2 2026", "the second quarter of 2026",
                   "Q2'26", "fiscal 2025"); tags always normalized ("2026Q2", "FY2025")
  values           several money formats ("$1.2B", "$1.2 billion", "C$1,200M")
  traps            WRONG_TIME, WRONG_INTENT, ECOSYSTEM (competitor / parent / subsidiary),
                   WRONG_RELATION (reversed, role swap, different relation), UNRESOLVED (generic ref,
                   pronoun, homonym, missing period), CONTEXT (industry, macro), PARTIAL (segment,
                   sub-period, in-range point for trend questions), IRRELEVANT (other sectors)

Still a scaffold: surface forms are template-driven. Paraphrase with paraphrase_synthetic.py and mix
with LLM-labeled real pairs before trusting a model trained on it.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
from collections import Counter
from dataclasses import dataclass, field

UTILITY = {
    "IRRELEVANT": 0.00, "ECOSYSTEM": 0.10, "WRONG_RELATION": 0.15, "WRONG_INTENT": 0.20,
    "UNRESOLVED": 0.25, "WRONG_TIME": 0.30, "CONTEXT": 0.40, "PARTIAL": 0.70, "DIRECT": 1.00,
}

# ---------------------------------------------------------------------------
# Fictional world
# ---------------------------------------------------------------------------
PREFIX = ["North", "Harbour", "Ash", "Pine", "Maple", "Cedar", "Granite", "Silver", "Iron", "Blue",
          "Red", "Stone", "Lake", "River", "Summit", "Birch", "Falcon", "Oak", "Elm", "Willow", "Copper",
          "Frost", "Glen", "Hawk", "Quarry", "Ridge", "Sable", "Thistle", "Vale", "Wren", "Arbor",
          "Brook", "Coral", "Dune", "Ember", "Fern", "Grove", "Heron", "Juniper", "Kestrel", "Lark",
          "Meadow", "Nimbus", "Orchard", "Prairie", "Rowan", "Spruce", "Tamarack", "Upland", "Verdant"]
SUFFIX = ["wind", "line", "grove", "crest", "field", "brook", "gate", "point", "view", "wood", "stone",
          "haven", "mark", "ford", "bridge", "hill", "light", "port", "shore", "well", "rock", "bay"]
KIND_NAMES = {
    "AM": ["Asset Management", "Investments", "Global Investors", "Capital Management", "Funds"],
    "BANK": ["Bank", "Financial", "Trust", "Bancorp"],
    "BD": ["Securities", "Wealth", "Brokerage", "Markets"],
    "INS": ["Life", "Insurance", "Assurance"],
}
GENERIC_REF = {
    "AM": ["the firm", "the manager", "the company", "the Toronto-based manager", "a large Canadian manager",
           "one rival manager", "its parent firm"],
    "BANK": ["the bank", "the lender", "the company", "a Big Six peer", "the Toronto-based lender", "one large bank"],
    "BD": ["the dealer", "the brokerage", "the firm", "a discount platform", "one online broker"],
    "INS": ["the insurer", "the company", "a large life insurer", "the Toronto-based insurer"],
}
PRONOUN = ["It", "The group"]
FIRST = ["Jane", "Marc", "Priya", "Daniel", "Aiko", "Luis", "Fatima", "Owen", "Chloe", "Ravi", "Elena",
         "Tomas", "Grace", "Hamid", "Nina", "Victor", "Sara", "Kofi", "Ingrid", "Paul"]
LAST = ["Arden", "Bellamy", "Castell", "Drummond", "Ellery", "Fairbanks", "Garnier", "Holloway", "Ivers",
        "Jarrow", "Kingsley", "Lindqvist", "Marlowe", "Northcott", "Okafor", "Pellerin", "Quaid", "Rowntree"]
REGULATORS = ["the Provincial Securities Board", "the Northern Markets Authority", "the Federal Prudential Office",
              "the Investment Dealers Council", "the Coastal Securities Commission", "the National Insurance Board"]
OTHER_SECTOR = ["Foods", "Logistics", "Mining", "Pharma", "Airlines", "Retail", "Energy", "Telecom", "Motors",
                "Media", "Shipping", "Steel"]


@dataclass(eq=False)
class Firm:
    stem: str
    full: str
    kind: str
    ticker: str
    homonym: bool = False
    competitors: list = field(default_factory=list)
    parent: "Firm | None" = None
    subs: list = field(default_factory=list)


def make_world(rng, n):
    stems, firms = {}, []
    while len(firms) < n:
        stem = rng.choice(PREFIX) + rng.choice(SUFFIX)
        kind = rng.choice(list(KIND_NAMES))
        full = f"{stem} {rng.choice(KIND_NAMES[kind])}"
        if any(f.full == full for f in stems.get(stem, [])):
            continue
        if stem in stems and (len(stems[stem]) >= 2 or rng.random() > 0.12):
            continue                                      # ~12% of stems get a homonym twin
        ticker = (stem[:2] + "".join(w[0] for w in full.split()[1:])).upper()[:4]
        f = Firm(stem, full, kind, ticker)
        stems.setdefault(stem, []).append(f)
        firms.append(f)
    for group in stems.values():
        if len(group) > 1:
            for f in group:
                f.homonym = True
    by_kind = {}
    for f in firms:
        by_kind.setdefault(f.kind, []).append(f)
    for f in firms:
        peers = [p for p in by_kind[f.kind] if p is not f and p.stem != f.stem]
        f.competitors = rng.sample(peers, k=min(3, len(peers)))
        if f.kind != "BANK" and rng.random() < 0.3:
            banks = [b for b in by_kind.get("BANK", []) if b.stem != f.stem]
            if banks:
                f.parent = rng.choice(banks)
                f.parent.subs.append(f)
    return firms


def person(rng):
    return f"{rng.choice(FIRST)} {rng.choice(LAST)}"


def name(f: Firm, rng, allow_alias=True):
    """Surface name + link status. Homonyms always use the full name when they must resolve."""
    r = rng.random()
    if allow_alias and r < 0.12:
        return f.ticker, "ALIAS"
    if f.homonym or r < 0.35:
        return f.full, "MATCH"
    return f.stem, "MATCH"


# ---------------------------------------------------------------------------
# Periods
# ---------------------------------------------------------------------------
YEARS = list(range(2018, 2027))
QWORD = {1: "first", 2: "second", 3: "third", 4: "fourth"}


def p_quarter(rng, y=None):
    y = y or rng.choice(YEARS); q = rng.randint(1, 4)
    return {"kind": "Q", "y": y, "q": q, "tag": f"{y}Q{q}", "lo": y + (q - 1) / 4, "hi": y + q / 4}


def p_half(rng, y=None):
    y = y or rng.choice(YEARS); h = rng.randint(1, 2)
    return {"kind": "H", "y": y, "h": h, "tag": f"{y}H{h}", "lo": y + (h - 1) / 2, "hi": y + h / 2}


def p_year(rng, y=None):
    y = y or rng.choice(YEARS)
    return {"kind": "Y", "y": y, "tag": f"FY{y}", "lo": y, "hi": y + 1}


def p_text(p, rng):
    if p["kind"] == "Q":
        y, q = p["y"], p["q"]
        return rng.choice([f"Q{q} {y}", f"Q{q} {y}", f"the {QWORD[q]} quarter of {y}", f"Q{q}'{str(y)[2:]}",
                           f"{q}Q{str(y)[2:]}"])
    if p["kind"] == "H":
        return rng.choice([f"H{p['h']} {p['y']}", f"the {'first' if p['h'] == 1 else 'second'} half of {p['y']}"])
    return rng.choice([f"{p['y']}", f"{p['y']}", f"fiscal {p['y']}", f"FY{p['y']}"])


def p_other(rng, p):
    gen = {"Q": p_quarter, "H": p_half, "Y": p_year}[p["kind"]]
    while True:
        o = gen(rng)
        if o["hi"] <= p["lo"] or o["lo"] >= p["hi"]:
            return o


def p_inside(rng, p):
    """A strictly smaller period inside p (a quarter inside a year or half; a half inside a year)."""
    if p["kind"] == "Y":
        return rng.choice([p_quarter, p_half])(rng, p["y"])
    if p["kind"] == "H":
        q = rng.choice([1, 2]) + (p["h"] - 1) * 2
        y = p["y"]
        return {"kind": "Q", "y": y, "q": q, "tag": f"{y}Q{q}", "lo": y + (q - 1) / 4, "hi": y + q / 4}
    return None


# ---------------------------------------------------------------------------
# Values
# ---------------------------------------------------------------------------
def money(v, rng):
    if v >= 1:
        return rng.choice([f"${v:.1f}B", f"${v:.1f} billion", f"C${v:.1f}B", f"${int(round(v * 1000)):,}M"])
    m = int(round(v * 1000))
    return rng.choice([f"${m}M", f"${m} million", f"C${m}M"])


def count(v, rng):
    return f"{int(round(v)):,}"


def pct(v, rng):
    return rng.choice([f"{v:.2f}%", f"{v:.2f} per cent"])


def bps(v, rng):
    return f"{int(round(v))} basis points"


RATINGS = ["AAA", "AA+", "AA", "AA-", "A+", "A", "A-", "BBB+", "BBB"]

# ---------------------------------------------------------------------------
# Attributes (intent). {E}=name {P}=period {V}=value
# ---------------------------------------------------------------------------
ATTRS = {
    "net_flows": dict(kinds={"AM", "INS"}, phrase="net flows", val=lambda r: r.uniform(0.1, 4.0), show=money,
        q=["What were {E}'s net flows in {P}?", "How much net new money did {E} gather in {P}?",
           "What net sales did {E} report for {P}?", "{E} net inflows {P}?"],
        c=["{E} took in {V} of net flows in {P}.", "{E} gathered {V} in net new money in {P}.",
           "In {P}, {E} reported {V} of net sales.", "{E} saw net inflows of {V} in {P}."],
        subset=["{E}'s fixed income funds took in {V} in {P}.", "{E}'s ETF lineup gathered {V} in {P}.",
                "{E}'s retail channel drew {V} of net sales in {P}."],
        context=["Canadian fund industry net flows reached {V} in {P}.", "Industry-wide ETF inflows hit {V} in {P}.",
                 "Falling rates drove record bond fund demand in {P}."]),
    "aum": dict(kinds={"AM", "BD", "INS"}, phrase="assets under management", val=lambda r: r.uniform(5, 300), show=money,
        q=["What were {E}'s assets under management at the end of {P}?", "How large was {E}'s AUM in {P}?",
           "What AUM did {E} report for {P}?"],
        c=["{E} ended {P} with {V} in assets under management.", "{E}'s AUM stood at {V} in {P}.",
           "In {P}, {E} managed {V} in client assets."],
        subset=["{E}'s ETF assets reached {V} in {P}.", "{E}'s institutional mandates totalled {V} in {P}."],
        context=["Total Canadian mutual fund assets reached {V} in {P}.", "Equity markets rallied sharply in {P}."]),
    "mgmt_fee": dict(kinds={"AM"}, phrase="management fees", val=lambda r: r.choice([0.25, 0.35, 0.45, 0.6, 0.75, 0.9, 1.1, 1.5]), show=pct,
        q=["What management fee did {E} charge on its flagship equity fund in {P}?",
           "What did {E} set its flagship fund's fee at in {P}?"],
        c=["{E} set its flagship equity fund fee at {V} in {P}.", "{E}'s flagship equity fund charged {V} in {P}.",
           "In {P}, {E} cut its flagship fund fee to {V}."],
        subset=["{E}'s F-series flagship units charged {V} in {P}."],
        context=["Average Canadian equity fund fees fell to {V} in {P}.", "Fee compression accelerated across the industry in {P}."]),
    "revenue": dict(kinds={"AM", "BANK", "BD", "INS"}, phrase="revenue", val=lambda r: r.uniform(0.2, 12), show=money,
        q=["What revenue did {E} report for {P}?", "How much revenue did {E} earn in {P}?", "{E} revenue {P}?"],
        c=["{E} reported {V} of revenue for {P}.", "{E} earned {V} in revenue in {P}.", "In {P}, {E}'s revenue came to {V}."],
        subset=["{E}'s wealth division earned {V} in revenue in {P}.", "{E}'s Canadian segment reported {V} of revenue for {P}."],
        context=["Canadian financial sector revenue grew to {V} in {P}.", "Trading volumes surged across Canadian markets in {P}."]),
    "net_income": dict(kinds={"BANK", "BD", "INS", "AM"}, phrase="net income", val=lambda r: r.uniform(0.05, 4), show=money,
        q=["What net income did {E} report for {P}?", "How much did {E} earn after tax in {P}?"],
        c=["{E} posted net income of {V} for {P}.", "{E} earned {V} after tax in {P}."],
        subset=["{E}'s retail bank earned {V} after tax in {P}.", "{E}'s capital markets arm posted {V} of profit in {P}."],
        context=["Canadian bank profits rose to {V} in aggregate in {P}.", "Credit losses climbed across the sector in {P}."]),
    "headcount": dict(kinds={"AM", "BANK", "BD", "INS"}, phrase="headcount", val=lambda r: r.randint(30, 9000), show=count,
        q=["How many employees did {E} have in {P}?", "What was {E}'s headcount in {P}?"],
        c=["{E} employed {V} people in {P}.", "{E}'s headcount reached {V} in {P}."],
        subset=["{E}'s Toronto office had {V} staff in {P}.", "{E} employed {V} advisors in {P}."],
        context=["Canadian wealth firms employed {V} advisors in {P}.", "Financial-sector hiring slowed in {P}."]),
    "fund_launches": dict(kinds={"AM"}, phrase="fund launches", val=lambda r: r.randint(4, 30), show=count,
        q=["How many new funds did {E} launch in {P}?", "How many products did {E} bring to market in {P}?"],
        c=["{E} launched {V} new funds in {P}.", "{E} brought {V} products to market in {P}."],
        subset=["{E} launched {V} new ETFs in {P}."],
        context=["Canadian managers launched {V} funds industry-wide in {P}."]),
    "client_accounts": dict(kinds={"BD", "BANK"}, phrase="client accounts", val=lambda r: r.randint(20, 2500) * 1000, show=count,
        q=["How many client accounts did {E} have in {P}?", "How many self-directed accounts did {E} hold in {P}?"],
        c=["{E} held {V} client accounts in {P}.", "{E} reported {V} accounts in {P}."],
        subset=["{E} held {V} TFSA accounts in {P}.", "{E} opened {V} new accounts in {P}."],
        context=["Canadian discount brokerages held {V} accounts in {P}."]),
    "dividend": dict(kinds={"BANK", "INS"}, phrase="dividend", val=lambda r: r.uniform(0.2, 2.0), show=lambda v, r: f"${v:.2f} per share",
        q=["What quarterly dividend did {E} declare in {P}?", "What was {E}'s dividend per share in {P}?"],
        c=["{E} declared a dividend of {V} in {P}.", "{E} raised its dividend to {V} in {P}."],
        subset=["{E} paid {V} on its preferred shares in {P}."],
        context=["Canadian banks raised dividends by {V} on average in {P}."]),
    "credit_rating": dict(kinds={"BANK", "INS", "BD"}, phrase="credit rating", val=lambda r: r.randrange(len(RATINGS)), show=lambda v, r: RATINGS[int(v) % len(RATINGS)],
        q=["What credit rating did {E} hold in {P}?", "How was {E} rated by the agencies in {P}?"],
        c=["{E} was rated {V} in {P}.", "Agencies affirmed {E} at {V} in {P}."],
        subset=["{E}'s covered bonds were rated {V} in {P}."],
        context=["Rating agencies held a stable outlook on Canadian banks in {P}."]),
    "market_share": dict(kinds={"AM", "BD", "BANK", "INS"}, phrase="market share", val=lambda r: r.uniform(0.5, 25), show=pct,
        q=["What was {E}'s market share in {P}?", "What share of the market did {E} hold in {P}?"],
        c=["{E} held {V} of the market in {P}.", "{E}'s market share reached {V} in {P}."],
        subset=["{E} held {V} of the ETF market in {P}."],
        context=["The top five firms held {V} of the market in {P}."]),
    "branches": dict(kinds={"BANK"}, phrase="branch count", val=lambda r: r.randint(40, 1200), show=count,
        q=["How many branches did {E} operate in {P}?"],
        c=["{E} operated {V} branches in {P}.", "{E}'s branch network numbered {V} in {P}."],
        subset=["{E} operated {V} branches in Ontario in {P}."],
        context=["Canadian banks closed {V} branches in total in {P}."]),
}

# Relations. {A} acts on {B}. Persons {X}; regulators {R}; {V} money.
RELATIONS = {
    "acquired": dict(q=["Who acquired {B} in {P}?", "Which firm bought {B} in {P}?"],
        direct=["{A} completed its acquisition of {B} in {P}.", "{A} bought {B} in {P}."],
        reversed=["{B} acquired {A} in {P}.", "{B} completed its purchase of {A} in {P}."],
        other=["{A} and {B} signed a distribution partnership in {P}.", "{A} took a minority stake in {B} in {P}.",
               "{A} bid for {B} but walked away in {P}."]),
    "sued": dict(q=["Who filed a lawsuit against {B} in {P}?", "Which firm sued {B} in {P}?"],
        direct=["{A} sued {B} in {P}.", "{A} filed a lawsuit against {B} in {P}."],
        reversed=["{B} sued {A} in {P}.", "{B} filed a claim against {A} in {P}."],
        other=["{A} and {B} settled a contract dispute in {P}.", "{A} testified in {B}'s court case in {P}."]),
    "subadvisor": dict(q=["Which firm was hired to sub-advise {B}'s equity funds in {P}?"],
        direct=["{B} hired {A} to sub-advise its equity funds in {P}.", "{A} became sub-advisor on {B}'s equity funds in {P}."],
        reversed=["{A} hired {B} to sub-advise its equity funds in {P}."],
        other=["{B} fired {A} as sub-advisor in {P}.", "{A} and {B} co-launched an equity fund in {P}."]),
    "ceo": dict(person=True, q=["Who did {B} name as CEO in {P}?", "Who became {B}'s chief executive in {P}?"],
        direct=["{B} named {X} chief executive in {P}.", "{X} became CEO of {B} in {P}."],
        reversed=["{X} stepped down as CEO of {B} in {P}.", "{B} named {X} chief financial officer in {P}."],
        other=["{X} joined {B}'s board in {P}.", "{X} was considered for {B}'s CEO role in {P}."]),
    "fined": dict(regulator=True, q=["Which regulator fined {B} in {P}?", "Who penalized {B} in {P}?"],
        direct=["{R} fined {B} {V} in {P}.", "{B} paid a {V} penalty to {R} in {P}."],
        reversed=["{B} filed a complaint with {R} in {P}.", "{R} approved {B}'s new fund in {P}."],
        other=["{R} reviewed {B}'s sales practices in {P}.", "{R} cleared {B} of wrongdoing in {P}."]),
}

IRRELEVANT_TPL = ["{X} {S} opened three new plants in {P}.", "{X} {S} cut its dividend in {P}.",
                  "{X} {S} named a new CEO in {P}.", "{X} {S} expanded into Mexico in {P}.",
                  "{X} {S} recalled two product lines in {P}.", "{X} {S} signed a supply deal in {P}."]


# ---------------------------------------------------------------------------
def split_for(key: str) -> str:
    h = int(hashlib.md5(key.encode()).hexdigest(), 16) % 100
    return "train" if h < 80 else ("val" if h < 90 else "test")


def tag(ent=None, link=None, period=None, attr=None, extra=""):
    e = f"[ENT] {ent}:ORG" + (f"={link}" if link else "") if ent else "[ENT] NONE"
    if extra:
        e += f" | {extra}"
    t = f"[TIME] {period['tag']}" if period else "[TIME] NONE"
    return f"{e} {t}" + (f" [ATTR] {attr}" if attr else "")


def cap(s):
    return s[0].upper() + s[1:] if s else s


import re as _re
MISS = {"time": 0.15, "link": 0.10, "rng": random.Random(0)}


def extractor_miss(c_tags: str) -> str:
    """Simulate a real extractor that sometimes misses the period or the entity link, so the
    model can't learn WRONG_TIME / UNRESOLVED from tags alone."""
    r = MISS["rng"]
    if r.random() < MISS["time"]:
        c_tags = _re.sub(r"\[TIME\] \S+", "[TIME] NONE", c_tags)
    if r.random() < MISS["link"]:
        c_tags = c_tags.replace("=MATCH", "").replace("=ADJACENT", "").replace("=ALIAS", "")
        c_tags = c_tags.replace("[ENT] UNRESOLVED", "[ENT] NONE")
    return c_tags


class Q:
    def __init__(self, qid, question, q_tags, anchor):
        self.qid, self.question, self.q_tags, self.anchor, self.rows = qid, question, q_tags, anchor, []
        self._seen = set()

    def add(self, label, claim, c_tags, pert):
        claim = cap(claim.replace("  ", " "))
        if claim in self._seen:
            return
        self._seen.add(claim)
        self.rows.append({"qid": self.qid, "question": self.question, "q_tags": self.q_tags, "claim": claim,
                          "c_tags": extractor_miss(c_tags), "label": label, "utility": UTILITY[label], "perturbation": pert,
                          "split": split_for(self.anchor), "weight": 1.0, "source": "synthetic_v2"})


PCT_ATTRS = {"mgmt_fee", "market_share"}


def ctx_val(attr, num, rng):
    """Industry-level figure for CONTEXT claims: bigger for totals, similar for rates."""
    if attr == "credit_rating":
        return num
    if attr in PCT_ATTRS or attr == "dividend":
        return num * rng.uniform(0.8, 1.3)
    return num * rng.uniform(8, 40)


def irrelevant(qq, rng):
    qq.add("IRRELEVANT", rng.choice(IRRELEVANT_TPL).format(X=rng.choice(PREFIX) + rng.choice(SUFFIX),
           S=rng.choice(OTHER_SECTOR), P=p_text(p_year(rng), rng)), "[ENT] NONE [TIME] NONE", "other_sector")


def unresolved_claims(qq, rng, f, tpl, p, attr, fill):
    """Generic reference, pronoun, homonym stem, or the period dropped."""
    choice = rng.random()
    if f.homonym and choice < 0.4:
        ref, pert = f.stem, "homonym_stem"
    elif choice < 0.7:
        ref, pert = rng.choice(GENERIC_REF[f.kind]), "generic_reference"
    else:
        ref, pert = rng.choice(PRONOUN), "pronoun"
    claim = tpl.format(E=ref, P=p_text(p, rng), **fill).replace(f"{ref}'s", f"{ref}'s")
    per = p
    if rng.random() < 0.35:
        vague = rng.choice(["this spring", "last quarter", "earlier this year", "recently"])
        claim = tpl.format(E=ref, P="@@", **fill).replace("in @@", vague).replace("for @@", vague).replace("@@", vague)
        per, pert = None, pert + "+no_period"
    qq.add("UNRESOLVED", claim, tag(None, None, per, attr).replace("[ENT] NONE", "[ENT] UNRESOLVED"), pert)


def gen_point(rng, world, f, qid):
    attr = rng.choice([a for a, d in ATTRS.items() if f.kind in d["kinds"]])
    A = ATTRS[attr]
    p = rng.choice([p_quarter, p_quarter, p_half, p_year])(rng)
    num, show = A["val"](rng), A["show"]
    en, _ = name(f, rng, allow_alias=False)
    qq = Q(qid, A["q"][rng.randrange(len(A["q"]))].format(E=en, P=p_text(p, rng)), tag(f.full, None, p, attr), f.full)

    # DIRECT, sometimes twice (second phrasing, maybe via ticker)
    for k in range(2 if rng.random() < 0.3 else 1):
        n2, link = name(f, rng)
        qq.add("DIRECT", rng.choice(A["c"]).format(E=n2, P=p_text(p, rng), V=show(num, rng)),
               tag(f.full, link, p, attr), "none" if k == 0 else "second_source")
    # PARTIAL: segment, and a sub-period
    if attr not in ("credit_rating",):
        part = num * (rng.uniform(0.6, 0.95) if attr in PCT_ATTRS | {"dividend"} else rng.uniform(0.15, 0.7))
        n2, link = name(f, rng)
        qq.add("PARTIAL", rng.choice(A["subset"]).format(E=n2, P=p_text(p, rng), V=show(part, rng)), tag(f.full, link, p, attr), "segment")
    sub = p_inside(rng, p)
    if sub and attr not in ("mgmt_fee", "credit_rating", "dividend") and rng.random() < 0.6:
        n2, link = name(f, rng)
        qq.add("PARTIAL", rng.choice(A["c"]).format(E=n2, P=p_text(sub, rng), V=show(A["val"](rng), rng)), tag(f.full, link, sub, attr), "sub_period")
    # WRONG_TIME x1-2
    for _ in range(rng.choice([1, 2])):
        o = p_other(rng, p)
        n2, link = name(f, rng)
        qq.add("WRONG_TIME", rng.choice(A["c"]).format(E=n2, P=p_text(o, rng), V=show(A["val"](rng), rng)), tag(f.full, link, o, attr), "period_swap")
    # WRONG_INTENT x1-2
    alts = [a for a, d in ATTRS.items() if a != attr and f.kind in d["kinds"]]
    for a2 in rng.sample(alts, k=min(len(alts), rng.choice([1, 2]))):
        B = ATTRS[a2]
        n2, link = name(f, rng)
        qq.add("WRONG_INTENT", rng.choice(B["c"]).format(E=n2, P=p_text(p, rng), V=B["show"](B["val"](rng), rng)), tag(f.full, link, p, a2), "attribute_swap")
    # ECOSYSTEM: competitor, parent or subsidiary, same attribute and period
    adj_pool = [(c, "competitor") for c in f.competitors] + ([(f.parent, "parent")] if f.parent else []) + [(s, "subsidiary") for s in f.subs]
    for adj, kind in rng.sample(adj_pool, k=min(len(adj_pool), rng.choice([1, 2]))):
        ok = adj.kind in A["kinds"]
        B = A if ok else ATTRS["revenue"]
        n2, _ = name(adj, rng, allow_alias=False)
        qq.add("ECOSYSTEM", rng.choice(B["c"]).format(E=n2, P=p_text(p, rng), V=B["show"](B["val"](rng), rng)),
               tag(adj.full, "ADJACENT", p, attr if ok else "revenue"), f"entity_{kind}")
    # UNRESOLVED
    unresolved_claims(qq, rng, f, rng.choice(A["c"]), p, attr, {"V": show(num, rng)})
    # CONTEXT
    qq.add("CONTEXT", rng.choice(A["context"]).format(P=p_text(p, rng), V=show(ctx_val(attr, num, rng), rng)),
           tag(None, None, p, attr), "scope_industry_or_macro")
    irrelevant(qq, rng)
    return qq.rows


def gen_trend(rng, world, f, qid):
    attr = rng.choice([a for a, d in ATTRS.items() if f.kind in d["kinds"] and a not in ("credit_rating",)])
    A = ATTRS[attr]
    y1 = rng.choice(YEARS[:-3]); y2 = rng.choice([y for y in YEARS if y > y1 + 1])
    since = rng.random() < 0.5
    rng_p = {"kind": "R", "tag": f"FY{y1}-FY{y2}" if not since else f"FY{y1}-FY{YEARS[-1]}", "lo": y1, "hi": (y2 if not since else YEARS[-1]) + 1}
    en, _ = name(f, rng, allow_alias=False)
    qt = (f"How have {en}'s {A['phrase']} changed since {y1}?" if since else
          rng.choice([f"How did {en}'s {A['phrase']} trend between {y1} and {y2}?", f"What were {en}'s {A['phrase']} each year from {y1} to {y2}?"]))
    qq = Q(qid, qt, tag(f.full, None, rng_p, attr), f.full)
    inside = [y for y in YEARS if rng_p["lo"] <= y < rng_p["hi"]]
    outside = [y for y in YEARS if y < rng_p["lo"] or y >= rng_p["hi"]]
    # a multi-year summary is DIRECT; single in-range points are PARTIAL
    a, b = inside[0], inside[-1]
    n2, link = name(f, rng)
    qq.add("DIRECT", rng.choice([f"{n2}'s {A['phrase']} grew every year from {a} to {b}.",
                                 f"{n2}'s {A['phrase']} fell steadily between {a} and {b}.",
                                 f"{n2}'s {A['phrase']} roughly doubled from {a} to {b}."]),
           tag(f.full, link, rng_p, attr), "trend_summary")
    for y in rng.sample(inside, k=min(2, len(inside))):
        p = p_year(rng, y); n2, link = name(f, rng)
        qq.add("PARTIAL", rng.choice(A["c"]).format(E=n2, P=p_text(p, rng), V=A["show"](A["val"](rng), rng)), tag(f.full, link, p, attr), "in_range_point")
    for y in rng.sample(outside, k=min(rng.choice([1, 2]), len(outside))):
        p = p_year(rng, y); n2, link = name(f, rng)
        qq.add("WRONG_TIME", rng.choice(A["c"]).format(E=n2, P=p_text(p, rng), V=A["show"](A["val"](rng), rng)), tag(f.full, link, p, attr), "out_of_range_point")
    alts = [x for x, d in ATTRS.items() if x != attr and f.kind in d["kinds"]]
    if alts:
        a2 = rng.choice(alts); B = ATTRS[a2]; p = p_year(rng, rng.choice(inside)); n2, link = name(f, rng)
        qq.add("WRONG_INTENT", rng.choice(B["c"]).format(E=n2, P=p_text(p, rng), V=B["show"](B["val"](rng), rng)), tag(f.full, link, p, a2), "attribute_swap")
    if f.competitors:
        c = rng.choice(f.competitors); n2, _ = name(c, rng, allow_alias=False)
        qq.add("ECOSYSTEM", f"{n2}'s {A['phrase']} grew every year from {a} to {b}.", tag(c.full, "ADJACENT", rng_p, attr), "entity_competitor")
    cp = p_year(rng, rng.choice(inside))
    qq.add("CONTEXT", rng.choice(A["context"]).format(P=p_text(cp, rng), V=A["show"](ctx_val(attr, A["val"](rng), rng), rng)),
           tag(None, None, cp, attr), "scope_industry_or_macro")
    ref = rng.choice(GENERIC_REF[f.kind])
    qq.add("UNRESOLVED", f"{cap(ref)}'s {A['phrase']} grew every year from {a} to {b}.", tag(None, None, rng_p, attr).replace("[ENT] NONE", "[ENT] UNRESOLVED"), "generic_reference")
    irrelevant(qq, rng)
    return qq.rows


def gen_relation(rng, world, f, qid):
    rel = rng.choice(list(RELATIONS)); R = RELATIONS[rel]
    p = rng.choice([p_year, p_year, p_quarter])(rng)
    a = rng.choice(f.competitors) if f.competitors else rng.choice(world)
    x, reg, val = person(rng), rng.choice(REGULATORS), money(rng.uniform(0.001, 0.2), rng)
    bn, _ = name(f, rng, allow_alias=False)
    qq = Q(qid, rng.choice(R["q"]).format(B=bn, P=p_text(p, rng)), tag(f.full, None, p, rel), f.full)
    other_ent = (f"{x}:PER" if R.get("person") else f"{reg}:REG" if R.get("regulator") else f"{a.full}:ORG")

    def fill(tpl, B=None, A=None, X=None, Rg=None, per=None):
        return tpl.format(A=A or name(a, rng, allow_alias=False)[0], B=B or name(f, rng, allow_alias=False)[0],
                          X=X or x, R=Rg or reg, V=val, P=p_text(per or p, rng))

    t = lambda link, per=p, extra=other_ent, ent=f.full: tag(ent, link, per, rel, extra)
    qq.add("DIRECT", fill(rng.choice(R["direct"])), t("MATCH"), "none")
    for tpl in rng.sample(R["reversed"], k=min(2, len(R["reversed"]))):
        qq.add("WRONG_RELATION", fill(tpl), t("MATCH"), "relation_reversed_or_role")
    qq.add("WRONG_RELATION", fill(rng.choice(R["other"])), t("MATCH"), "relation_type")
    o = p_other(rng, p)
    qq.add("WRONG_TIME", fill(rng.choice(R["direct"]), per=o), t("MATCH", o), "period_swap")
    others = [c for c in f.competitors if c is not a] or [w for w in world if w is not f and w is not a]
    c2 = rng.choice(others)
    qq.add("ECOSYSTEM", fill(rng.choice(R["direct"]), B=name(c2, rng, allow_alias=False)[0]), t("ADJACENT", ent=c2.full), "target_swap")
    ref = f.stem if f.homonym and rng.random() < 0.5 else rng.choice(GENERIC_REF[f.kind])
    qq.add("UNRESOLVED", fill(rng.choice(R["direct"]), B=ref), tag(None, None, p, rel, other_ent).replace("[ENT] NONE", "[ENT] UNRESOLVED"), "entity_unresolved")
    if rel in ("acquired", "ceo", "fined"):
        ctx = {"acquired": "Canadian wealth-management deal volume hit a record in {P}.",
               "ceo": "CEO turnover at Canadian financial firms rose sharply in {P}.",
               "fined": "Regulators issued more penalties against dealers in {P}."}[rel]
        qq.add("CONTEXT", ctx.format(P=p_text(p, rng)), tag(None, None, p, rel), "scope_industry")
    irrelevant(qq, rng)
    return qq.rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n_questions", type=int, default=12000)
    ap.add_argument("--n_entities", type=int, default=900)
    ap.add_argument("--mix", default="point:0.55,trend:0.15,relation:0.30")
    ap.add_argument("--out", default="data/synthetic.jsonl")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--miss_time", type=float, default=0.15, help="share of claims whose period tag is missed")
    ap.add_argument("--miss_link", type=float, default=0.10, help="share of claims whose entity link is missed")
    args = ap.parse_args()
    rng = random.Random(args.seed)
    MISS.update(time=args.miss_time, link=args.miss_link, rng=random.Random(args.seed + 1))
    world = make_world(rng, args.n_entities)
    mix = [(k, float(v)) for k, v in (x.split(":") for x in args.mix.split(","))]
    gens = {"point": gen_point, "trend": gen_trend, "relation": gen_relation}
    rows, qtypes = [], Counter()
    for i in range(args.n_questions):
        f = rng.choice(world)
        kind = rng.choices([k for k, _ in mix], weights=[w for _, w in mix])[0]
        qtypes[kind] += 1
        rows += gens[kind](rng, world, f, f"syn2-{i:06d}")
    with open(args.out, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    lab, spl, pert = Counter(r["label"] for r in rows), Counter(r["split"] for r in rows), Counter(r["perturbation"] for r in rows)
    print(f"wrote {len(rows):,} pairs for {args.n_questions:,} questions -> {args.out}")
    print("question types:", dict(qtypes))
    print("labels:", dict(sorted(lab.items(), key=lambda x: -x[1])))
    print("splits:", dict(spl))
    print("perturbations:", len(pert), "kinds")


if __name__ == "__main__":
    main()
