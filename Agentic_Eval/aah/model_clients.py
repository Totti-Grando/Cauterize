"""Provider-agnostic LLM backends for the evaluator role.

The evaluator components (question gen, rubric gen, nli/judge scorers, note-taker, updater)
all call an Anthropic-style ``client.messages.create(model, max_tokens, system, messages)``
and read ``.content[0].text``. This module supplies drop-in clients with that exact shape
backed by **Groq** (its OpenAI-compatible API), so those components can run on Groq's open
models with no change. Anthropic remains available as the native client.

Two clients are returned per backend because the pipeline uses a *sync* client for the
generator/rubric/note-taker/updater and an *async* client for the scorers (which ``await``).
Temperature 0 is sent to Groq for determinism (Groq/OpenAI accept it; Anthropic Opus does not,
so the native path omits it — see spec §9).
"""

from __future__ import annotations

import asyncio
import os
import time
from types import SimpleNamespace
from typing import Any, Optional

import httpx

GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
# Bedrock model IDs are provider-prefixed; global routing is the default for Opus 4.6.
DEFAULT_BEDROCK_EVAL_MODEL = "global.anthropic.claude-opus-4-6-v1"
_MAX_RETRIES = 5          # retry transient rate-limit / server errors
_BACKOFF_BASE = 2.0       # seconds; exponential, capped
_BACKOFF_CAP = 30.0


def _retry_after(response: httpx.Response, attempt: int) -> float:
    """Seconds to wait: honor Retry-After if present, else capped exponential backoff."""
    header = response.headers.get("retry-after")
    if header:
        try:
            return min(float(header), _BACKOFF_CAP)
        except ValueError:
            pass
    return min(_BACKOFF_BASE * (2 ** attempt), _BACKOFF_CAP)


def _should_retry(status: int) -> bool:
    return status == 429 or status >= 500
# Groq's Llama 3.x defaults were decommissioned; the currently-served open models are the
# gpt-oss family (see `GET /openai/v1/models`). Override per-run with --eval-model/--target-model.
DEFAULT_GROQ_EVAL_MODEL = "openai/gpt-oss-120b"
DEFAULT_GROQ_TARGET_MODEL = "openai/gpt-oss-20b"


def _openai_messages(system: Optional[str], messages: list[dict]) -> list[dict]:
    out: list[dict] = []
    if system:
        out.append({"role": "system", "content": system})
    for m in messages:
        out.append({"role": m.get("role", "user"), "content": m.get("content", "")})
    return out


def _wrap(text: str) -> Any:
    """Return an object shaped like an Anthropic Messages response (.content[0].text)."""
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=text or "")])


def _payload(model: str, max_tokens: int, system: Optional[str], messages: list[dict]) -> dict:
    return {
        "model": model,
        "messages": _openai_messages(system, messages),
        "max_tokens": max_tokens,
        "temperature": 0,
    }


def _content(data: dict) -> str:
    try:
        return data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError):
        return ""


class _GroqSyncMessages:
    def __init__(self, key: str):
        self._key = key

    def create(self, *, model: str, messages: list[dict], max_tokens: int = 1024,
               system: Optional[str] = None, **_ignore: Any) -> Any:
        payload = _payload(model, max_tokens, system, messages)
        headers = {"Authorization": f"Bearer {self._key}"}
        for attempt in range(_MAX_RETRIES):
            r = httpx.post(GROQ_CHAT_URL, headers=headers, json=payload, timeout=120)
            if _should_retry(r.status_code) and attempt < _MAX_RETRIES - 1:
                time.sleep(_retry_after(r, attempt))
                continue
            r.raise_for_status()
            return _wrap(_content(r.json()))


class GroqClient:
    """Sync client that quacks like ``anthropic.Anthropic()`` for the evaluator components."""

    def __init__(self, api_key: str):
        self.messages = _GroqSyncMessages(api_key)


class _GroqAsyncMessages:
    def __init__(self, key: str):
        self._key = key

    async def create(self, *, model: str, messages: list[dict], max_tokens: int = 1024,
                     system: Optional[str] = None, **_ignore: Any) -> Any:
        payload = _payload(model, max_tokens, system, messages)
        headers = {"Authorization": f"Bearer {self._key}"}
        async with httpx.AsyncClient(timeout=120) as c:
            for attempt in range(_MAX_RETRIES):
                r = await c.post(GROQ_CHAT_URL, headers=headers, json=payload)
                if _should_retry(r.status_code) and attempt < _MAX_RETRIES - 1:
                    await asyncio.sleep(_retry_after(r, attempt))
                    continue
                r.raise_for_status()
                return _wrap(_content(r.json()))


class AsyncGroqClient:
    """Async client that quacks like ``anthropic.AsyncAnthropic()`` for the scorers."""

    def __init__(self, api_key: str):
        self.messages = _GroqAsyncMessages(api_key)


def resolve_groq_key() -> Optional[str]:
    """Find the Groq key from an explicit variable only.

    Previously this scanned EVERY environment variable's value for a ``gsk_`` prefix, which could
    non-deterministically pick up an unrelated secret and authenticate with the wrong key (audit
    finding #19). Resolution is now limited to the documented ``GROQ_API_KEY``.
    """
    return os.environ.get("GROQ_API_KEY") or None


def _bedrock_kwargs() -> dict:
    """AWS config for the Bedrock clients, read from the environment.

    Only ``aws_region`` is passed explicitly; credentials resolve via the SDK's default AWS
    chain (``AWS_ACCESS_KEY_ID``/``AWS_SECRET_ACCESS_KEY``[/``AWS_SESSION_TOKEN``], ``AWS_PROFILE``
    + ~/.aws/credentials, an IAM role, or ``AWS_BEARER_TOKEN_BEDROCK``). The SDK defaults the
    region to ``AWS_REGION`` and then ``us-east-1``; we pass it through when set for clarity.
    """
    region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION")
    return {"aws_region": region} if region else {}


def make_evaluator(backend: str, model: Optional[str] = None) -> tuple[Any, Any, str]:
    """Return ``(sync_client, async_client, model)`` for the evaluator role.

    ``sync_client`` drives the generator / rubric / note-taker / updater; ``async_client``
    drives the nli / judge scorers. Supported backends: ``groq``, ``anthropic``, ``bedrock``.
    """
    backend = backend.lower()
    if backend == "anthropic":
        import anthropic
        return anthropic.Anthropic(), anthropic.AsyncAnthropic(), (model or "claude-opus-4-8")
    if backend == "bedrock":
        # Claude on Amazon Bedrock: same messages.create surface, so the Claude* components
        # run unchanged. Requires `pip install "anthropic[bedrock]"` at runtime.
        import anthropic
        kwargs = _bedrock_kwargs()
        return (
            anthropic.AnthropicBedrock(**kwargs),
            anthropic.AsyncAnthropicBedrock(**kwargs),
            model or DEFAULT_BEDROCK_EVAL_MODEL,
        )
    if backend == "groq":
        key = resolve_groq_key()
        if not key:
            raise RuntimeError("no Groq key found (set GROQ_API_KEY, or a gsk_... value, in .env)")
        return GroqClient(key), AsyncGroqClient(key), (model or DEFAULT_GROQ_EVAL_MODEL)
    raise ValueError(f"unknown evaluator backend {backend!r} (use groq | anthropic | bedrock)")
