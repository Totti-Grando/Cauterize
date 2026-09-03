"""Omission as a banded rate with a confidence interval + minimum sample (G14).

Completeness / agent false-negatives are measured as **source-recall + seeded-catch**: of the
material facts (and the deliberately planted "seeded" documents) that should appear, the fraction the
answer surfaces. The rate is reported with a Wilson confidence interval and a minimum sample size —
below the minimum the metric **abstains** from a band rather than assert a rate on noise.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

_DEFAULT_MIN_SAMPLE = 10
_Z = 1.96  # 95% CI


def wilson_interval(successes: int, n: int, z: float = _Z) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion (stable at small n / extreme rates)."""
    if n <= 0:
        return (0.0, 1.0)
    phat = successes / n
    denom = 1 + z * z / n
    centre = (phat + z * z / (2 * n)) / denom
    half = (z * math.sqrt(phat * (1 - phat) / n + z * z / (4 * n * n))) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


@dataclass(frozen=True)
class OmissionResult:
    value: Optional[float]        # combined recall (higher_is_better); None if abstained
    ci_low: Optional[float]
    ci_high: Optional[float]
    sample_size: int
    abstained: bool
    reason: str = ""


def omission_metric(context: dict, *, min_sample: int = _DEFAULT_MIN_SAMPLE) -> OmissionResult:
    """Combined source-recall + seeded-catch with a Wilson CI.

    ``context`` supplies ``source_found``/``source_total`` and ``seeded_found``/``seeded_total``.
    Below ``min_sample`` total the metric abstains (no band asserted).
    """
    found = int(context.get("source_found", 0)) + int(context.get("seeded_found", 0))
    total = int(context.get("source_total", 0)) + int(context.get("seeded_total", 0))
    if total < min_sample:
        return OmissionResult(None, None, None, total, True,
                              f"below_min_sample ({total} < {min_sample})")
    low, high = wilson_interval(found, total)
    return OmissionResult(round(found / total, 4), round(low, 4), round(high, 4), total, False)
