"""NLI claim-check scorer slot (spec §6: ``nli``) — a CONSTRAINED yes/no supported-check.

Answers "is the claim in ``question.text`` supported by ``context``?" with a tight yes/no prompt
at temperature 0 — deliberately narrower than the general judge (F9). Three interchangeable
backends fill the same router slot:

* :class:`ClaudeNLIScorer`  — Anthropic client (default; injectable for offline tests).
* :class:`HttpNLIScorer`    — any JSON-over-HTTP endpoint (internal gateway / self-hosted),
  configured with base URL + model + auth; the request/response shape is configurable.
* :class:`LocalNLIScorer`   — optional MiniCheck/AlignScore behind the OPTIONAL ``nli_local``
  dependency group. Imported lazily, so the BASE install stays torch/transformers-free.

Determinism on Opus 4.8 comes from the model's low-variance behavior plus the harness's 2-run
averaging guard (spec §9); the Claude path omits the (rejected) temperature parameter, the HTTP
path sends temperature 0 for OpenAI-compatible gateways.
"""

from __future__ import annotations

import copy
from typing import Any, Awaitable, Callable, Optional

from ...contracts import BinaryQuestion, Verdict
from .base import (
    SPOTLIGHT_SYSTEM,
    extract_text,
    first_decision,
    looks_like_steer,
    parse_obj_json,
    wrap_untrusted,
)

_SYSTEM = (
    "You are a strict natural-language-inference checker. Given CONTEXT and a CLAIM, "
    "decide whether the CONTEXT supports (entails) the CLAIM. A claim is supported only "
    "if the context provides evidence for it; if the context is silent or contradicts it, "
    "it is NOT supported. Numbers count as supported when they are semantically "
    "equivalent (e.g. '83rd minute' vs 'seven minutes left' in a 90-minute match). "
    'Respond with ONLY a JSON object: {"supported": true|false, "reason": "<short>"}.'
) + SPOTLIGHT_SYSTEM


class ClaudeNLIScorer:
    """Claim-check scorer: supported claim -> score 1, unsupported -> score 0."""

    def __init__(self, client: Any = None, model: str = "claude-opus-4-8"):
        self._client = client
        self._model = model

    def _get_client(self) -> Any:
        """Lazily build an ``anthropic.AsyncAnthropic()`` client on first use."""
        if self._client is None:
            import anthropic

            self._client = anthropic.AsyncAnthropic()
        return self._client

    async def score(
        self, question: BinaryQuestion, response: str, context: str
    ) -> Verdict:
        client = self._get_client()
        message = await client.messages.create(
            model=self._model,
            max_tokens=1024,
            system=_SYSTEM,
            messages=[
                {
                    "role": "user",
                    "content": f"CONTEXT (untrusted data):\n{wrap_untrusted(context)}\n\n"
                               f"CLAIM (trusted):\n{question.text}",
                }
            ],
        )
        text = extract_text(message)
        supported, reason = _interpret(text)
        return Verdict(
            question_id=question.id,
            score=1 if supported else 0,
            explanation=reason,
            evidence=text or None,
        )


def _interpret(text: str) -> tuple[bool, str]:
    """Map the model's reply to ``(supported, explanation)``; explanation is never empty.

    F2: fail CLOSED (unsupported) on a steer-y or unparseable reply.
    """
    if looks_like_steer(text):
        return False, "possible prompt-injection in judged content; failed closed (unsupported)"
    data = parse_obj_json(text)
    if data is not None and isinstance(data.get("supported"), bool):
        supported = bool(data["supported"])
        reason = str(data.get("reason") or "").strip()
    else:
        # Conservative fallback: decide on the first whole-word signal; default unsupported.
        decided = first_decision(
            text, ("yes", "true", "supported"), ("no", "false", "not supported", "unsupported")
        )
        supported = bool(decided) if decided is not None else False
        reason = (text or "").strip()
    if not reason:
        reason = "claim is supported by the context" if supported else (
            "claim is not supported by the context"
        )
    return supported, reason


# --- HTTP-endpoint NLI backend (F9) ---------------------------------------------------
Poster = Callable[[str, dict, dict], Awaitable[dict]]


async def _httpx_poster(url: str, headers: dict, payload: dict) -> dict:
    import httpx  # local import keeps module import cheap

    from ...llm import _MAX_RETRIES, _retry_after, _should_retry

    async with httpx.AsyncClient(timeout=60) as client:
        for attempt in range(_MAX_RETRIES):
            r = await client.post(url, headers=headers, json=payload)
            if _should_retry(r.status_code) and attempt < _MAX_RETRIES - 1:
                import asyncio
                await asyncio.sleep(_retry_after(r, attempt))
                continue
            r.raise_for_status()
            return r.json()
    return {}


def _get_path(obj: Any, path: str) -> Any:
    cur = obj
    for part in path.split("."):
        try:
            cur = cur[int(part)] if part.isdigit() else cur[part]
        except (KeyError, IndexError, TypeError):
            return ""
    return cur


class HttpNLIScorer:
    """Constrained NLI claim-check against a configurable JSON-over-HTTP endpoint (F9).

    Points at any OpenAI-compatible gateway or internal claim-check service. Sends the tight
    supported? prompt at temperature 0; auth via a bearer token from ``api_key_env``. Injectable
    ``poster`` keeps unit tests offline.
    """

    def __init__(
        self,
        url: str,
        *,
        model: str = "",
        api_key_env: Optional[str] = None,
        response_path: str = "choices.0.message.content",
        poster: Optional[Poster] = None,
    ):
        self._url = url
        self._model = model
        self._api_key_env = api_key_env
        self._response_path = response_path
        self._poster = poster or _httpx_poster

    async def score(self, question: BinaryQuestion, response: str, context: str) -> Verdict:
        import os

        payload: dict = {
            "messages": [
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": f"CONTEXT (untrusted data):\n{wrap_untrusted(context)}\n\n"
                                            f"CLAIM (trusted):\n{question.text}"},
            ],
            "temperature": 0,
        }
        if self._model:
            payload["model"] = self._model
        headers = {"Content-Type": "application/json"}
        if self._api_key_env and os.environ.get(self._api_key_env):
            headers["Authorization"] = f"Bearer {os.environ[self._api_key_env]}"
        data = await self._poster(self._url, headers, copy.deepcopy(payload))
        text = _get_path(data, self._response_path)
        supported, reason = _interpret(text if isinstance(text, str) else str(text))
        return Verdict(question_id=question.id, score=1 if supported else 0, explanation=reason,
                       evidence="nli:http")


class LocalNLIScorer:
    """Optional local MiniCheck/AlignScore claim-checker (OPTIONAL ``nli_local`` extra).

    Imported lazily so the base install carries no torch/transformers. Install with
    ``pip install "aah[nli_local]"`` (or the pinned minicheck deps) to enable.
    """

    def __init__(self, model: str = "minicheck"):
        self._model = model
        self._checker = None

    def _get(self):
        if self._checker is None:
            try:
                from minicheck.minicheck import MiniCheck  # type: ignore
            except ImportError as exc:  # pragma: no cover - optional dep
                raise RuntimeError(
                    "LocalNLIScorer requires the optional 'nli_local' dependency group "
                    "(pip install \"aah[nli_local]\"). Use ClaudeNLIScorer or HttpNLIScorer instead."
                ) from exc
            self._checker = MiniCheck(model_name=self._model)
        return self._checker

    async def score(self, question: BinaryQuestion, response: str, context: str) -> Verdict:
        import asyncio

        def _run():
            pred, _raw, _ = self._get().score(docs=[context], claims=[question.text])
            return int(pred[0])

        score = await asyncio.to_thread(_run)
        return Verdict(question_id=question.id, score=score,
                       explanation="local NLI claim-check", evidence="nli:local")


def make_nli(config: Optional[dict] = None, *, client: Any = None, model: str = "claude-opus-4-8"):
    """Build the NLI scorer for the router slot from optional config.

    config = {"backend": "claude"|"http"|"local", ...}. Defaults to the constrained Claude NLI.
    """
    cfg = config or {}
    backend = (cfg.get("backend") or "claude").lower()
    if backend == "http":
        return HttpNLIScorer(cfg["url"], model=cfg.get("model", ""),
                             api_key_env=cfg.get("api_key_env"),
                             response_path=cfg.get("response_path", "choices.0.message.content"))
    if backend == "local":
        return LocalNLIScorer(model=cfg.get("model", "minicheck"))
    return ClaudeNLIScorer(client=client, model=cfg.get("model") or model)
