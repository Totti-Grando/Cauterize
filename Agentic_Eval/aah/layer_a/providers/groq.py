"""Groq provider-under-test adapter (OpenAI-compatible chat completions).

Lets a Groq-served open model (e.g. Llama 3.1) be the agent under test, behind the same
:class:`ProviderAdapter` interface as Gemini. The key is auto-detected via the shared
``resolve_groq_key`` (``GROQ_API_KEY`` or any ``gsk_...`` value).
"""

from __future__ import annotations

import asyncio

import httpx

from ...model_clients import (
    GROQ_CHAT_URL,
    DEFAULT_GROQ_TARGET_MODEL,
    _MAX_RETRIES,
    _retry_after,
    _should_retry,
    resolve_groq_key,
)
from .base import ProviderAdapter


class GroqProvider(ProviderAdapter):
    name = "groq"

    def __init__(self, model: str = DEFAULT_GROQ_TARGET_MODEL, api_key: str | None = None):
        self._model = model
        self._api_key = api_key

    async def query(self, question: str) -> str:
        key = self._api_key or resolve_groq_key()
        payload = {
            "model": self._model,
            "messages": [{"role": "user", "content": question}],
            "max_tokens": 1024,
            "temperature": 0,
        }
        headers = {"Authorization": f"Bearer {key}"}
        async with httpx.AsyncClient(timeout=120) as client:
            for attempt in range(_MAX_RETRIES):
                r = await client.post(GROQ_CHAT_URL, headers=headers, json=payload)
                if _should_retry(r.status_code) and attempt < _MAX_RETRIES - 1:
                    await asyncio.sleep(_retry_after(r, attempt))
                    continue
                break
        r.raise_for_status()
        data = r.json()
        try:
            return data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError):
            return ""
