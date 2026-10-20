# Training data catalog

Built 2026-10-20 by `build_dataset.py`. Mix: 112,292 rows, 12,000 questions. Hold-out: 0 rows (never in the mix).

## Sources

| Source | Kind | Status | Rows on disk | Produced by | Licence |
| --- | --- | --- | --- | --- | --- |
| llm_labeled_real | real | TODO | 0 | label_real.py on your pipeline pairs | yours |
| synthetic_v2 | synthetic | ready | 112,295 | generate_synthetic.py (included) | yours |
| synthetic_v2_para | synthetic | TODO | 0 | paraphrase_synthetic.py | yours |
| twowiki | public | TODO | 0 | fetch_public.py --sources twowiki | check repo licence |
| tempreason | public | TODO | 0 | fetch_public.py --sources tempreason | check dataset card |
| musique | public | TODO | 0 | fetch_public.py --sources musique | not stated; check repo |
| hotpotqa | public | TODO | 0 | fetch_public.py --sources hotpotqa | CC BY-SA 4.0 (verify) |
| real_holdout | holdout | TODO | 0 | label_real.py --holdout + your adjudication | yours |

## Class coverage in the mix (rows)

| Source | DIRECT | PARTIAL | WRONG_INTENT | WRONG_TIME | WRONG_RELATION | ECOSYSTEM | UNRESOLVED | CONTEXT | IRRELEVANT | Total |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| synthetic_v2 | 13,834 | 11,056 | 11,605 | 15,741 | 10,156 | 15,377 | 11,999 | 10,524 | 12,000 | 112,292 |
| **All** | **13,834** | **11,056** | **11,605** | **15,741** | **10,156** | **15,377** | **11,999** | **10,524** | **12,000** | **112,292** |

## Train share by kind

- synthetic: 100.0%

## Readiness

- Real labeled data: MISSING - run label_real.py
- Real hold-out set: MISSING - run label_real.py --holdout
- Untagged rows: 0
- Public rows capped: 0; duplicate/leaking rows removed: 0
