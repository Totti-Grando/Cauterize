"""Backend-owned config catalogs the UI presents on the setup wizard pages.

These are legitimately server-side: the list of selectable models, the connectable
provider integrations, the QA modes, and a sample source inventory. They mirror the
shapes the React pages expect (see Possible_UI/frontend/src/data/placeholders.js) so the
frontend renders identically whether it is talking to the mock layer or this server.
"""

from __future__ import annotations

# Selectable primary (evaluator) models. `id` values line up with RunContext's label map.
MODELS = [
    {"id": "anthropic.claude-sonnet", "label": "Claude Sonnet", "note": "Balanced reasoning · recommended", "tier": "Balanced"},
    {"id": "anthropic.claude-haiku", "label": "Claude Haiku", "note": "Fast · lower cost", "tier": "Fast"},
    {"id": "anthropic.claude-opus", "label": "Claude Opus", "note": "Deepest reasoning", "tier": "Deep"},
    {"id": "amazon.titan-text", "label": "Titan Text", "note": "Amazon foundation model", "tier": "General"},
    {"id": "custom", "label": "Custom Bedrock Model ID", "note": "Bring your own model id", "tier": "Custom"},
]

# Secondary providers (systems under test). `id` values line up with RunContext's label map.
PROVIDERS = [
    {
        "id": "ravenpack",
        "name": "RavenPack",
        "description": "News & document analytics provider with entity-level sentiment and event detection.",
        "outputType": "Structured analytics + narrative",
        "linkSupport": True,
        "evidenceSupport": True,
        "accent": "brand",
        # Credentials the UI must collect before this provider can be used.
        "requiredCredentials": ["api_key"],
    },
    {
        "id": "nexa",
        "name": "Nexa",
        "description": "Research-grounded assistant for market and issuer-level questions.",
        "outputType": "Narrative answer with citations",
        "linkSupport": True,
        "evidenceSupport": True,
        "accent": "violet",
        "requiredCredentials": ["api_key", "bearer_token"],
    },
    {
        "id": "custom",
        "name": "Custom Provider",
        "description": "Connect any chatbot or research API via a custom endpoint definition.",
        "outputType": "Configurable",
        "linkSupport": False,
        "evidenceSupport": False,
        "accent": "slate",
        "requiredCredentials": ["endpoint", "api_key"],
    },
]

# Human labels + input hints for each credential field (used by the setup modals).
CREDENTIAL_FIELDS = {
    "api_key": {"label": "API key", "secret": True},
    "bearer_token": {"label": "Bearer token", "secret": True},
    "endpoint": {"label": "Endpoint URL", "secret": False, "placeholder": "https://api.example.com/v1/chat"},
}

MODES = [
    {
        "id": "manual",
        "title": "You control everything",
        "name": "Manual Mode",
        "description": "Write or paste your own questions. The system sends them to the secondary provider and evaluates the answers.",
        "icon": "PencilLine",
    },
    {
        "id": "assisted",
        "title": "Suggested but still in your power",
        "name": "Assisted Mode",
        "description": "The system suggests QA pairs. You review, edit, approve, reject, or regenerate before running.",
        "icon": "Sparkles",
    },
    {
        "id": "automatic",
        "title": "Fully automatic — watch the program run",
        "name": "Fully Automatic Mode",
        "description": "The system generates questions, queries the selected provider, evaluates the outputs, and produces a full results report.",
        "icon": "Workflow",
    },
]

# Sample source inventory (documents + links + a quality rollup). Illustrative only.
SOURCE_DOCUMENTS = [
    {"id": "d1", "name": "Q3_Issuer_Briefing.pdf", "type": "PDF", "size": "2.4 MB", "status": "extracted"},
    {"id": "d2", "name": "Reputational_Risk_Memo.docx", "type": "DOCX", "size": "684 KB", "status": "extracted"},
    {"id": "d3", "name": "Regulatory_Notes.txt", "type": "TXT", "size": "38 KB", "status": "review"},
]

SOURCE_LINKS = [
    {"id": "l1", "url": "https://research.example.com/issuer/esg-controversy-aug", "sourceType": "Research article", "fetchStatus": "success", "extractStatus": "extracted"},
    {"id": "l2", "url": "https://newswire.example.com/2026/regulatory-inquiry", "sourceType": "Newswire", "fetchStatus": "success", "extractStatus": "extracted"},
    {"id": "l3", "url": "https://portal.example.com/secure/filings", "sourceType": "SharePoint", "fetchStatus": "login", "extractStatus": "blocked"},
]

SOURCE_QUALITY = [
    {"label": "Extractable text", "count": 4, "tone": "success"},
    {"label": "Login page detected", "count": 1, "tone": "warning"},
    {"label": "Empty source", "count": 0, "tone": "neutral"},
    {"label": "Needs review", "count": 1, "tone": "warning"},
]


def provider_label(provider_id: str | None) -> str:
    """Map a provider id to its display name (defaults to RavenPack)."""
    for p in PROVIDERS:
        if p["id"] == provider_id:
            return p["name"]
    return "RavenPack"
