"""Real Gemini provider-under-test adapter (spec §5 step 3a).

Wraps ``google.generativeai`` behind the :class:`ProviderAdapter` interface. The model
client is injectable so unit tests run fully offline; at runtime it is lazily built from
``GEMINI_API_KEY`` with a temperature-0 generation config for deterministic queries.
"""

from __future__ import annotations

import asyncio
import os

from .base import ProviderAdapter


class GeminiProvider(ProviderAdapter):
    name = "gemini"

    def __init__(
        self,
        model: str = "gemini-1.5-pro",
        api_key: str | None = None,
        client=None,
    ):
        self._model = model
        self._api_key = api_key
        self._client = client

    def _get_client(self):
        """Lazily build a GenerativeModel (temperature 0) on first use."""
        if self._client is None:
            import google.generativeai as genai

            api_key = self._api_key or os.environ.get("GEMINI_API_KEY")
            genai.configure(api_key=api_key)
            self._client = genai.GenerativeModel(
                self._model,
                generation_config={"temperature": 0},
            )
        return self._client

    async def query(self, question: str) -> str:
        client = self._get_client()
        # The SDK call is synchronous; offload it so we don't block the event loop.
        response = await asyncio.to_thread(client.generate_content, question)

        # Handle empty / blocked responses gracefully.
        text = getattr(response, "text", None)
        if not text:
            return ""
        return text
