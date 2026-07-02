"""Quality "seeds" -- the QuestionGenerator input (spec §5 step 2). [M1 owner: A1]

A seed is the small, human-authored spark that the (meta-prompt-driven) QuestionGenerator
expands into a full domain question. It names the domain, optionally points at a source
document, and optionally carries free-form authoring instructions. ``seed_to_text`` renders
a seed to the plain string the generator consumes alongside ``P_Q``.

Loading is permissive about format: ``load_seed_file`` reads JSON or YAML (YAML only if
PyYAML is installed); ``load_seed`` validates a plain dict.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, Union

from pydantic import BaseModel, ConfigDict


class Seed(BaseModel):
    """Frozen QuestionGenerator input.

    Attributes:
        domain: The subject area the generated question should live in (e.g. "finance").
        source_doc: Optional grounding text / document the question must be answerable from.
        instructions: Optional free-form authoring guidance for the generator.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    domain: str
    source_doc: Optional[str] = None
    instructions: Optional[str] = None


def load_seed(d: dict) -> Seed:
    """Validate and build a :class:`Seed` from a plain dict."""
    return Seed(**d)


def load_seed_file(path: Union[str, Path]) -> Seed:
    """Load a :class:`Seed` from a JSON or YAML file (by extension)."""
    path = Path(path)
    raw = path.read_text(encoding="utf-8")

    suffix = path.suffix.lower()
    if suffix in {".yaml", ".yml"}:
        try:
            import yaml
        except ImportError as exc:  # pragma: no cover - depends on optional dep
            raise RuntimeError(
                "PyYAML is required to load YAML seed files; install pyyaml or use JSON."
            ) from exc
        data = yaml.safe_load(raw)
    else:
        data = json.loads(raw)

    if not isinstance(data, dict):
        raise ValueError(f"Seed file {path} must contain a mapping, got {type(data).__name__}")
    return load_seed(data)


def seed_to_text(seed: Seed) -> str:
    """Render a seed to the string the QuestionGenerator consumes."""
    lines = [f"Domain: {seed.domain}"]
    if seed.instructions:
        lines.append(f"Instructions: {seed.instructions}")
    if seed.source_doc:
        lines.append("Source document:")
        lines.append(seed.source_doc)
    return "\n".join(lines)


# --- Ready-made example seeds -------------------------------------------------

FINANCE_SUMMARY_SEED = Seed(
    domain="finance",
    source_doc=(
        "Acme Corp Q3 FY24 results: revenue $4.2B (up 8% YoY), operating margin 21%, "
        "free cash flow $0.9B. Management guided Q4 revenue to $4.4-4.6B."
    ),
    instructions=(
        "Ask the model to summarize the key financial results faithfully; the question "
        "should be answerable only from the source document above."
    ),
)

SUPPORT_FAQ_SEED = Seed(
    domain="customer_support",
    instructions=(
        "Ask a realistic product-support question whose correct answer requires the "
        "model to abstain or ask for clarification when information is missing."
    ),
)

EXAMPLE_SEEDS: dict[str, Seed] = {
    "finance_summary": FINANCE_SUMMARY_SEED,
    "support_faq": SUPPORT_FAQ_SEED,
}
