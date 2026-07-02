"""Provider-under-test adapters. Real Gemini adapter (M1) + deterministic fixture."""

from .base import ProviderAdapter
from .fixture import FixtureProvider
from .gemini import GeminiProvider
from .http import HttpProvider

__all__ = ["ProviderAdapter", "FixtureProvider", "GeminiProvider", "HttpProvider"]
