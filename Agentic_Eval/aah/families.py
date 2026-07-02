"""Model-family detection for self-enhancement-bias control (F1 flag, F4 routing).

A judge from the same model family as the system-under-test tends to favor same-family output
(self-enhancement bias). We detect the family from the backend + model id heuristically; an
unknown family returns "" and is never treated as a same-family match.
"""

from __future__ import annotations


def model_family(backend: str, model: str) -> str:
    """Coarse model family from backend + model id. "" when unknown (never a same-family match)."""
    text = f"{backend or ''} {model or ''}".lower()
    if any(k in text for k in ("claude", "anthropic", "bedrock")):
        return "anthropic"
    if any(k in text for k in ("gemini", "google")):
        return "google"
    if any(k in text for k in ("llama", "groq")):  # groq serves Llama-family models
        return "meta"
    if any(k in text for k in ("gpt", "openai")):
        return "openai"
    if "mistral" in text:
        return "mistral"
    return ""


def same_family(a_backend: str, a_model: str, b_backend: str, b_model: str) -> bool:
    """True only when both resolve to the SAME non-empty family."""
    fa = model_family(a_backend, a_model)
    fb = model_family(b_backend, b_model)
    return bool(fa) and fa == fb
