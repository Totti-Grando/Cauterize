"""Server-side settings + secrets store for the UI.

The frontend Settings page configures AWS/Bedrock, the evaluator LLM backend, and the
secondary providers (endpoints + API keys). Those secrets live here in a single JSON file
(``aah/api/config.json``, gitignored) — never in the browser and never committed.

Two hard rules:
  * ``masked()`` is the ONLY shape sent to the browser: raw secrets are replaced by
    ``{"configured": bool, "last4": str}``.
  * When the UI PUTs settings back, a secret field whose value is the mask sentinel
    (or a dict / the literal bullet mask) means "unchanged" — we keep the stored value.

``apply_to_env()`` exports the stored credentials into ``os.environ`` so the existing
engine code (``make_evaluator`` / the provider adapters) resolves them through its normal
AWS/keys chain with no further plumbing.
"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any

from ..logging_config import get_logger

log = get_logger("api.config_store")

_CONFIG_PATH = Path(__file__).resolve().parent / "config.json"

# A field the browser sends back unchanged: we must not overwrite the stored secret with it.
_MASK_SENTINELS = {"", "••••••••••••••••", "********"}

# Which leaf keys are secrets (masked on read, sentinel-preserved on write).
_SECRET_KEYS = {"access_key_id", "secret_access_key", "session_token", "bearer_token", "api_key"}


def _default_config() -> dict[str, Any]:
    """The seed config. Provider defaults mirror static_data (ravenpack/nexa/custom)."""
    return {
        "aws": {
            "region": "us-east-1",
            "access_key_id": "",
            "secret_access_key": "",
            "session_token": "",
            "profile": "",
            "bearer_token": "",
        },
        "evaluator": {
            "backend": "bedrock",   # bedrock | groq | anthropic
            "model": "",            # empty => backend default (see aah/llm.py)
        },
        "bedrock": {
            "default_model": "anthropic.claude-sonnet",
            "enabled_model_ids": [
                "anthropic.claude-sonnet",
                "anthropic.claude-haiku",
                "anthropic.claude-opus",
            ],
            "custom_models": [],    # [{id, label}]
            "max_tokens": 4096,
            "temperature": 0.2,
        },
        # Long-term storage: when enabled + a bucket is set, S3 is the primary run-history
        # store (local runs.jsonl becomes an offline cache). AWS creds come from the `aws`
        # section above via apply_to_env(); no extra secrets here.
        "s3": {
            "enabled": False,
            "bucket": "",
            "prefix": "aah",
            "region": "",   # empty => fall back to aws.region
        },
        "providers": {
            "ravenpack": {
                "name": "RavenPack", "enabled": True, "adapter": "http",
                "api_key": "", "bearer_token": "", "endpoint": "", "question_path": "prompt",
                "response_path": "choices.0.message.content", "model": "",
                "request_evidence": True,
            },
            "nexa": {
                "name": "Nexa", "enabled": True, "adapter": "http",
                "api_key": "", "bearer_token": "", "endpoint": "", "question_path": "prompt",
                "response_path": "choices.0.message.content", "model": "",
                "request_evidence": True,
            },
            "custom": {
                "name": "Custom Provider", "enabled": False, "adapter": "http",
                "api_key": "", "bearer_token": "", "endpoint": "", "question_path": "prompt",
                "response_path": "choices.0.message.content", "model": "",
                "request_evidence": False,
            },
        },
    }


def _deep_merge(base: dict, patch: dict, *, preserve_secret_sentinels: bool) -> dict:
    """Recursively merge ``patch`` into ``base`` (mutating ``base``).

    When ``preserve_secret_sentinels`` is set, a secret leaf equal to a mask sentinel is
    dropped from the patch so the stored value survives.
    """
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value, preserve_secret_sentinels=preserve_secret_sentinels)
        else:
            if (
                preserve_secret_sentinels
                and key in _SECRET_KEYS
                and (not isinstance(value, str) or value in _MASK_SENTINELS)
            ):
                continue  # unchanged secret -> keep what we have
            base[key] = value
    return base


def _mask_value(value: str) -> dict[str, Any]:
    v = value or ""
    return {"configured": bool(v), "last4": v[-4:] if len(v) >= 4 else ""}


def _mask(node: Any, parent_key: str | None = None) -> Any:
    if isinstance(node, dict):
        return {k: _mask(v, k) for k, v in node.items()}
    if isinstance(node, list):
        return [_mask(v) for v in node]
    if parent_key in _SECRET_KEYS and isinstance(node, str):
        return _mask_value(node)
    return node


class ConfigStore:
    """Load/merge/persist UI settings; expose masked reads and env application."""

    def __init__(self, path: Path = _CONFIG_PATH):
        self._path = path
        self._data = _default_config()
        self.load()

    # --- persistence --------------------------------------------------------------
    def load(self) -> None:
        if self._path.exists():
            try:
                stored = json.loads(self._path.read_text(encoding="utf-8"))
                # Merge onto defaults so new keys appear for old files (no secret masking here).
                self._data = _deep_merge(_default_config(), stored, preserve_secret_sentinels=False)
                log.info("config loaded from %s", self._path.name)
            except (ValueError, OSError) as exc:
                log.warning("config unreadable (%s); using defaults", exc)
                self._data = _default_config()
        else:
            log.info("no config file yet; using defaults")

    def save(self) -> None:
        self._path.write_text(json.dumps(self._data, indent=2), encoding="utf-8")
        log.info("config saved to %s", self._path.name)

    # --- reads --------------------------------------------------------------------
    def raw(self) -> dict[str, Any]:
        """Full config INCLUDING secrets. Server-side use only — never send to the browser."""
        return copy.deepcopy(self._data)

    def masked(self) -> dict[str, Any]:
        """Browser-safe view: secrets become {configured, last4}."""
        return _mask(copy.deepcopy(self._data))

    def get_provider(self, provider_id: str) -> dict[str, Any]:
        return copy.deepcopy(self._data.get("providers", {}).get(provider_id, {}))

    @property
    def aws(self) -> dict[str, Any]:
        return self._data.get("aws", {})

    @property
    def evaluator(self) -> dict[str, Any]:
        return self._data.get("evaluator", {})

    @property
    def bedrock(self) -> dict[str, Any]:
        return self._data.get("bedrock", {})

    @property
    def s3(self) -> dict[str, Any]:
        return self._data.get("s3", {})

    # --- writes -------------------------------------------------------------------
    def update(self, patch: dict[str, Any]) -> None:
        _deep_merge(self._data, patch, preserve_secret_sentinels=True)

    # --- env application ----------------------------------------------------------
    def apply_to_env(self) -> None:
        """Export stored credentials so make_evaluator / adapters resolve them normally."""
        aws = self._data.get("aws", {})
        mapping = {
            "AWS_REGION": aws.get("region"),
            "AWS_DEFAULT_REGION": aws.get("region"),
            "AWS_ACCESS_KEY_ID": aws.get("access_key_id"),
            "AWS_SECRET_ACCESS_KEY": aws.get("secret_access_key"),
            "AWS_SESSION_TOKEN": aws.get("session_token"),
            "AWS_PROFILE": aws.get("profile"),
            "AWS_BEARER_TOKEN_BEDROCK": aws.get("bearer_token"),
        }
        applied = [k for k, v in mapping.items() if v]
        for env_key, value in mapping.items():
            if value:
                os.environ[env_key] = value
        log.info("applied AWS env vars: %s", ", ".join(applied) or "(none)")

        # Provider keys: expose groq/gemini/anthropic keys under their standard env vars
        # so the corresponding adapters (which fall back to env) also work.
        for prov in self._data.get("providers", {}).values():
            key = prov.get("api_key")
            adapter = prov.get("adapter")
            if not key:
                continue
            if adapter == "groq":
                os.environ.setdefault("GROQ_API_KEY", key)
            elif adapter == "gemini":
                os.environ.setdefault("GEMINI_API_KEY", key)
            elif adapter == "anthropic":
                os.environ.setdefault("ANTHROPIC_API_KEY", key)


# Module-level singleton used by the server.
store = ConfigStore()
