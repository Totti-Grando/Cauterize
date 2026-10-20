"""
Plug your entity system in here so public and paraphrased rows carry the same tags as real rows.

build_dataset.py calls these for any row whose tags are empty. Return strings in the same format
your pipeline produces (see README "Row format"):

    tag_question("What were Northwind's net flows in Q2 2026?")
        -> "[ENT] Northwind Asset Management:ORG [TIME] 2026Q2 [ATTR] net_flows"
    tag_claim(q_tags, "Northwind took in $1.2B in Q2 2026.")
        -> "[ENT] Northwind Asset Management:ORG=MATCH [TIME] 2026Q2 [ATTR] net_flows"

Until you wire it up, both return "" and the rows train untagged, which is still valid (the model
sees untagged input 30% of the time anyway through tag dropout). build_dataset.py reports how many
rows went untagged.
"""


def tag_question(question: str) -> str:
    return ""


def tag_claim(q_tags: str, claim: str) -> str:
    return ""


ENABLED = False   # set True once the two functions above call your extractor
