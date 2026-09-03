"""Generic HTTP provider-under-test adapter for custom / enterprise model APIs.

Wraps any JSON-over-HTTP endpoint (e.g. RavenPack or a bank's internal model) behind the
:class:`ProviderAdapter` interface, so it drops into the harness like Gemini or Groq. The
request/response shape is configured, not hard-coded:

- ``question_path``  -- dot path where the question is injected into the request body
  (e.g. ``"prompt"`` or ``"messages.0.content"``).
- ``response_path``  -- dot path to the answer text in the response JSON
  (e.g. ``"text"`` or ``"choices.0.message.content"``).
- ``base_payload``   -- fixed fields merged into every request (model name, params, ...).
- ``api_key_env``    -- env var holding a bearer token, added as an Authorization header.

The ``poster`` is injectable so unit tests run fully offline; at runtime it defaults to an
httpx POST with the shared retry/backoff.
"""

from __future__ import annotations

import copy
import os
from typing import Any, Awaitable, Callable, Optional

import httpx

from ...model_clients import _MAX_RETRIES, _retry_after, _should_retry
from .base import ProviderAdapter

Poster = Callable[[str, dict, dict], Awaitable[dict]]


def _set_path(obj: dict, path: str, value: Any) -> None:
    """Set ``value`` at a dot path, creating dicts / lists as needed (numeric hop => list)."""
    parts = path.split(".")
    cur: Any = obj
    for i, part in enumerate(parts):
        last = i == len(parts) - 1
        nxt = parts[i + 1] if not last else None
        child_is_list = nxt is not None and nxt.isdigit()
        if part.isdigit():
            idx = int(part)
            while len(cur) <= idx:
                cur.append(None)
            if last:
                cur[idx] = value
            else:
                if not isinstance(cur[idx], (dict, list)):
                    cur[idx] = [] if child_is_list else {}
                cur = cur[idx]
        else:
            if last:
                cur[part] = value
            else:
                if not isinstance(cur.get(part), (dict, list)):
                    cur[part] = [] if child_is_list else {}
                cur = cur[part]


def _get_path(obj: Any, path: str) -> Any:
    """Read a dot path from nested dicts / lists; returns '' if any hop is missing."""
    cur = obj
    for part in path.split("."):
        try:
            cur = cur[int(part)] if part.isdigit() else cur[part]
        except (KeyError, IndexError, TypeError):
            return ""
    return cur


async def _httpx_poster(url: str, headers: dict, payload: dict) -> dict:
    async with httpx.AsyncClient(timeout=120) as client:
        for attempt in range(_MAX_RETRIES):
            r = await client.post(url, headers=headers, json=payload)
            if _should_retry(r.status_code) and attempt < _MAX_RETRIES - 1:
                import asyncio
                await asyncio.sleep(_retry_after(r, attempt))
                continue
            r.raise_for_status()
            return r.json()
    return {}


class HttpProvider(ProviderAdapter):
    name = "http"

    def __init__(
        self,
        url: str,
        *,
        question_path: str = "prompt",
        response_path: str = "choices.0.message.content",
        base_payload: Optional[dict] = None,
        headers: Optional[dict] = None,
        api_key_env: Optional[str] = None,
        auth_header: str = "Authorization",
        auth_prefix: str = "Bearer ",
        poster: Optional[Poster] = None,
    ):
        self._url = url
        self._question_path = question_path
        self._response_path = response_path
        self._base_payload = base_payload or {}
        self._headers = headers or {}
        self._api_key_env = api_key_env
        self._auth_header = auth_header
        self._auth_prefix = auth_prefix
        self._poster = poster or _httpx_poster

    async def query(self, question: str) -> str:
        payload = copy.deepcopy(self._base_payload)
        _set_path(payload, self._question_path, question)

        headers = {"Content-Type": "application/json", **self._headers}
        if self._api_key_env:
            token = os.environ.get(self._api_key_env)
            if token:
                headers[self._auth_header] = f"{self._auth_prefix}{token}"

        data = await self._poster(self._url, headers, payload)
        text = _get_path(data, self._response_path)
        return text if isinstance(text, str) else ("" if text is None else str(text))
