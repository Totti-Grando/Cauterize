"""Deterministic fixture provider (spec §11: tiny fixture before any real adapter).

Canned responses keyed by question, with a default fallback. Used for the deterministic
integration test and for Layer B loop tests, where reproducibility matters more than realism.
"""

from __future__ import annotations

from .base import ProviderAdapter


class FixtureProvider(ProviderAdapter):
    name = "fixture"

    def __init__(self, responses: dict[str, str] | None = None, default: str = ""):
        self._responses = responses or {}
        self._default = default

    async def query(self, question: str) -> str:
        return self._responses.get(question, self._default)
