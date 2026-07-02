"""ProviderAdapter interface -- the provider-under-test boundary (spec §5 step 3a).

The fixture provider (deterministic) and the real Gemini adapter both implement this.
The pipeline depends only on this interface, so swapping providers is one constructor arg.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class ProviderAdapter(ABC):
    """Query the agent being evaluated. Async to support the §5 fork."""

    name: str = "provider"

    @abstractmethod
    async def query(self, question: str) -> str:
        """Return the provider's response to ``question``."""
        raise NotImplementedError
