"""FastAPI app exposing the aah engine to the Possible_UI frontend.

Serves ``/api/*`` on :8000 to match the Vite dev proxy. Run it with
``python run_server.py`` from the project root, or ``uvicorn aah.api.server:app``.

Endpoints:
  * setup catalogs   — /models, /providers, /modes, /sources (config-aware via config_store)
  * settings/secrets — /settings (GET masked / PUT), /settings/test, /bedrock/models
  * streaming modes  — /manual/turn, /assisted/draft, /run/stream (SSE)
  * results/export    — /evaluations, /run/monitor, /runs, /runs/{id}/export

Runs go through ``engine.py``: real Bedrock/provider calls when credentials are configured,
with graceful fallback to the deterministic ``scenario.py`` fixtures otherwise.
"""

from __future__ import annotations

import csv
import io
import json
from typing import Any, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

from . import engine
from . import static_data as sd
from ..contracts import Mode
from ..logging_config import get_logger
from .adapter import audit_to_evaluation
from .config_store import store as config_store
from .run_store import store as run_store
from .scenario import CASES, run_scenario

log = get_logger("api.server")

app = FastAPI(title="Agent Assurance Harness API", version="0.1.0")

# Apply any stored credentials to the environment so the engine resolves them.
config_store.apply_to_env()

_s3 = config_store.s3 or {}
_backend = f"S3 (bucket={_s3.get('bucket')})" if _s3.get("enabled") and _s3.get("bucket") else "local JSONL"
log.info("API starting - run store: %s; evaluator ready: %s", _backend, engine.evaluator_ready(config_store))

# The Vite proxy makes same-origin requests, but allow direct :5173 access too.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- in-memory store (single-process dev state; swap for real persistence later) ----
class _Store:
    def __init__(self) -> None:
        self.last_evaluations: list[dict] = []
        self.extra_links: list[dict] = []
        self.runs: list[dict] = list(_SEED_RUNS)
        # Provenance of the most recent streamed run — the AUTHORITATIVE live/fixture status,
        # used to stamp saved runs (audit #8) rather than trusting the client-supplied labels.
        self.last_run_live: bool = False
        self.last_run_detail: str = ""


_SEED_RUNS: list[dict] = [
    {
        "runId": "RUN-2026-0612-A", "date": "2026-06-12 14:22", "user": "p.intraligi",
        "documents": 3, "links": 3, "primaryModel": "Claude Sonnet", "provider": "RavenPack",
        "mode": "Assisted", "questions": 5,
        "verdictSummary": {"correct": 1, "partial": 2, "incorrect": 1, "unverifiable": 1},
        "exportStatus": "exported", "notes": "Reputational-risk sweep for issuer briefing.",
    },
    {
        "runId": "RUN-2026-0610-B", "date": "2026-06-10 09:05", "user": "p.intraligi",
        "documents": 2, "links": 1, "primaryModel": "Claude Opus", "provider": "Nexa",
        "mode": "Automatic", "questions": 8,
        "verdictSummary": {"correct": 5, "partial": 2, "incorrect": 0, "unverifiable": 1},
        "exportStatus": "pending", "notes": "Regulatory follow-up. Strong groundedness overall.",
    },
]

store = _Store()


# --- request bodies -----------------------------------------------------------------
class LinkBody(BaseModel):
    url: str


class GenerateBody(BaseModel):
    mode: Optional[str] = None
    provider: Optional[str] = None
    questionCount: Optional[int] = None
    focusAreas: Optional[list[str]] = None


class RunBody(BaseModel):
    mode: Optional[str] = None
    provider: Optional[str] = None


# --- setup / catalog endpoints ------------------------------------------------------
@app.get("/api/models")
def get_models() -> list[dict]:
    """Enabled Bedrock models (curated + custom) for the model picker."""
    catalog = engine.list_bedrock_models(config_store, refresh=False)["models"]
    enabled = [m for m in catalog if m.get("enabled", True)]
    return [{"id": m["id"], "label": m["label"], "note": m.get("note", ""), "tier": m.get("tier", "")}
            for m in enabled] or sd.MODELS


@app.get("/api/providers")
def get_providers() -> list[dict]:
    """Secondary providers with per-credential status so the UI can prompt for what's missing."""
    out = []
    for p in sd.PROVIDERS:
        cfg = config_store.get_provider(p["id"])
        required = p.get("requiredCredentials", [])
        cred_status = {f: bool(cfg.get(f)) for f in required}
        out.append({
            **p,
            "enabled": cfg.get("enabled", True),
            "credentialsStatus": cred_status,
            "missingCredentials": [f for f, ok in cred_status.items() if not ok],
            "credentialFields": {f: sd.CREDENTIAL_FIELDS.get(f, {"label": f, "secret": True}) for f in required},
            "configured": all(cred_status.values()) if required else True,
        })
    return out


@app.get("/api/aws/status")
def aws_status() -> dict[str, Any]:
    """Whether the Bedrock evaluator has usable credentials (for the model-setup prompt)."""
    aws = config_store.raw().get("aws", {})
    return {
        "region": aws.get("region", ""),
        "configured": engine.evaluator_ready(config_store),
        "hasKeys": bool(aws.get("access_key_id") and aws.get("secret_access_key")),
        "hasProfile": bool(aws.get("profile")),
        "hasBearer": bool(aws.get("bearer_token")),
    }


@app.get("/api/modes")
def get_modes() -> list[dict]:
    return sd.MODES


@app.get("/api/sources")
def get_sources() -> dict[str, Any]:
    return {
        "documents": sd.SOURCE_DOCUMENTS,
        "links": sd.SOURCE_LINKS + store.extra_links,
        "quality": sd.SOURCE_QUALITY,
    }


@app.post("/api/sources/links")
def add_link(body: LinkBody) -> dict:
    link = {
        "id": f"l-{len(store.extra_links) + 100}",
        "url": body.url,
        "sourceType": "Research article",
        "fetchStatus": "success",
        "extractStatus": "extracted",
    }
    store.extra_links.append(link)
    return link


# --- settings (config + secrets) ----------------------------------------------------
class SettingsTestBody(BaseModel):
    provider: Optional[str] = None


@app.get("/api/settings")
def get_settings() -> dict[str, Any]:
    """Masked config — secrets returned as {configured, last4}, never raw."""
    return config_store.masked()


@app.put("/api/settings")
def put_settings(body: dict) -> dict[str, Any]:
    """Merge + persist settings (masked-sentinel secrets are preserved), then apply to env."""
    config_store.update(body)
    config_store.save()
    config_store.apply_to_env()
    return config_store.masked()


@app.post("/api/settings/test")
async def test_settings(body: SettingsTestBody) -> dict[str, Any]:
    """Probe the evaluator and (optionally) a provider connection. Never raises."""
    result: dict[str, Any] = {"evaluator": engine.test_evaluator(config_store)}
    if body.provider:
        result["provider"] = await engine.test_provider(config_store, body.provider)
    return result


@app.get("/api/bedrock/models")
def bedrock_models(refresh: bool = False) -> dict[str, Any]:
    """Curated + custom models; when refresh=true and creds allow, merge the live AWS catalog."""
    return engine.list_bedrock_models(config_store, refresh=refresh)


# --- questions / evaluation (the real-engine vertical slice) ------------------------
@app.post("/api/questions/generate")
def generate_questions(body: GenerateBody) -> list[dict]:
    """Proposed QA pairs for Assisted mode — drawn from the scenario cases."""
    return [
        {
            "id": c.id,
            "persona": c.persona,
            "category": c.category,
            "difficulty": c.difficulty,
            "focus": c.focus,
            "text": c.question,
            "why": c.why,
            "expected": c.expected,
            "status": c.status,
        }
        for c in CASES
    ]


@app.post("/api/evaluations/run")
async def run_evaluation(body: RunBody) -> list[dict]:
    """Run the whole scenario through the engine and return UI evaluation objects."""
    provider = sd.provider_label(body.provider)
    pairs = await run_scenario()
    evaluations = [
        audit_to_evaluation(
            record,
            {
                "id": f"E-{case.id.split('-')[-1]}",
                "questionId": case.id,
                "provider": provider,
                "persona": case.persona,
                "category": case.category,
                "expected": case.expected,
                "evidence": case.evidence,
            },
        )
        for case, record in pairs
    ]
    store.last_evaluations = evaluations
    return evaluations


@app.get("/api/evaluations")
async def get_evaluations() -> list[dict]:
    if not store.last_evaluations:
        await run_evaluation(RunBody())
    return store.last_evaluations


# --- streaming mode flows (SSE) -----------------------------------------------------
class ManualBody(BaseModel):
    question: str
    context: Optional[str] = None
    provider: Optional[str] = None
    objective: Optional[str] = "learning"           # learning | attack (Layer B)
    lessons: Optional[list[dict]] = None            # client-accumulated deduped lessons


class DraftBody(BaseModel):
    provider: Optional[str] = None
    index: Optional[int] = 0


class RunStreamBody(BaseModel):
    mode: Optional[str] = None
    provider: Optional[str] = None
    questionCount: Optional[int] = None
    objective: Optional[str] = "learning"           # learning | attack (Layer B loop)


def _sse(gen) -> StreamingResponse:
    """Wrap an async event generator as a text/event-stream response."""

    async def _emit():
        async for event in gen:
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(
        _emit(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _stream_and_store(gen, *, append: bool):
    """Forward an event generator, persist its evaluations, and stamp live/fixture provenance.

    Accepts any async event generator (a single-plan `stream_eval` or the `stream_run_loop`).
    Provenance (#8) is read from the terminal `done` event so it works for both.
    """
    collected: list[dict] = []
    live, detail = False, ""
    async for event in gen:
        if event["type"] == "evaluation":
            collected.append(event["evaluation"])
        elif event["type"] == "done":
            live, detail = bool(event.get("live")), event.get("detail", "")
        yield event
    store.last_run_live, store.last_run_detail = live, detail
    log.info("stream finished - %d evaluations, live=%s (%s)", len(collected), live, detail or "n/a")
    if collected:
        store.last_evaluations = (store.last_evaluations + collected) if append else collected


@app.post("/api/manual/turn")
def manual_turn(body: ManualBody) -> StreamingResponse:
    """Manual/assisted turn — provider answers, answer is evaluated; Layer B lessons applied."""
    plan = engine.plan_manual(
        config_store, body.provider or "ravenpack", body.question, body.context,
        objective=(body.objective or "learning"), lessons=body.lessons or [],
    )
    return _sse(_stream_and_store(engine.stream_eval(plan), append=True))


@app.post("/api/assisted/draft")
def assisted_draft(body: DraftBody) -> dict[str, Any]:
    """Assisted mode: draft one question with reviewer tips."""
    return engine.draft_question(config_store, body.provider or "ravenpack", body.index or 0)


@app.get("/api/rubric")
def get_rubric() -> dict[str, Any]:
    """The evaluation rubric / config — the engine's source of truth (dimensions, tiers, gates,
    weighting, scorers, routing). Derived from the frozen policy table + default WeightConfig."""
    from .rubric_config import rubric_config

    return rubric_config()


@app.get("/api/objectives")
def get_objectives() -> list[dict]:
    """Layer B objectives the UI offers."""
    return [
        {"id": "learning", "name": "Learning", "description":
         "Lessons sharpen the evaluation each turn — the question is sent as-is."},
        {"id": "attack", "name": "Attack (red-team)", "description":
         "Lessons escalate the probe against the configured provider to test its robustness."},
    ]


@app.post("/api/run/stream")
def run_stream(body: RunStreamBody) -> StreamingResponse:
    """Automatic mode = the Layer B loop: N rounds, each fed by the prior round's lessons."""
    n = body.questionCount or len(CASES)
    objective = (body.objective or "learning").lower()
    gen = engine.stream_run_loop(config_store, body.provider or "ravenpack", objective, n)
    return _sse(_stream_and_store(gen, append=False))


# --- run monitor / history / export -------------------------------------------------
@app.get("/api/run/monitor")
async def run_monitor() -> dict[str, Any]:
    evals = store.last_evaluations or await get_evaluations()
    answered = len(evals)
    unsupported = sum(1 for e in evals if "unsupported_claim" in e["shortfalls"])
    unverifiable = sum(1 for e in evals if e["verdict"] == "unverifiable")
    steps = [
        {"step": "Reading sources", "status": "done", "message": "5 sources queued, 4 readable"},
        {"step": "Extracting text", "status": "done", "message": "4 documents extracted, 1 login page detected"},
        {"step": "Generating questions", "status": "done", "message": f"{len(CASES)} questions generated across personas"},
        {"step": "Querying secondary provider", "status": "done", "message": f"{answered} of {len(CASES)} answered"},
        {"step": "Evaluating groundedness", "status": "done", "message": "Deterministic rubric checks applied"},
        {"step": "Classifying shortfalls", "status": "done", "message": f"{unsupported} unsupported-claim flags"},
        {"step": "Writing results", "status": "done", "message": "Results ready for review"},
    ]
    log = [
        {"ts": "14:22:01", "step": "Reading sources", "status": "info", "message": "Queued 5 sources (3 docs, 3 links)"},
        {"ts": "14:22:09", "step": "Generating questions", "status": "success", "message": f"Generated {len(CASES)} questions"},
        {"ts": "14:22:18", "step": "Querying provider", "status": "success", "message": "Answers received"},
        {"ts": "14:22:24", "step": "Evaluating", "status": "success", "message": "Rubric checks complete"},
    ]
    metrics = [
        {"label": "Questions generated", "value": len(CASES), "tone": "neutral"},
        {"label": "Answers received", "value": answered, "tone": "neutral"},
        {"label": "Evaluations completed", "value": answered, "tone": "neutral"},
        {"label": "Unsupported claims found", "value": unsupported, "tone": "danger"},
        {"label": "Unverifiable answers", "value": unverifiable, "tone": "info"},
        {"label": "Sources extracted", "value": 4, "tone": "success"},
        {"label": "Links failed", "value": 1, "tone": "warning"},
    ]
    return {"steps": steps, "log": log, "metrics": metrics}


class SaveRunBody(BaseModel):
    mode: Optional[str] = None
    provider: Optional[str] = None
    primaryModel: Optional[str] = None
    documents: Optional[int] = 0
    links: Optional[int] = 0
    notes: Optional[str] = ""
    evaluations: Optional[list[dict]] = None  # omit -> use the last streamed run


@app.get("/api/runs")
def get_runs() -> list[dict]:
    """Saved runs (newest first) followed by the seeded sample rows."""
    return run_store.list() + _SEED_RUNS


@app.post("/api/runs")
def save_run(body: SaveRunBody) -> dict:
    """Persist a run to the history audit trail, stamped with authoritative live/fixture provenance."""
    evals = body.evaluations if body.evaluations is not None else store.last_evaluations
    rec = run_store.add(
        mode=body.mode or "Manual",
        provider=body.provider or "—",
        primary_model=body.primaryModel or "—",
        evaluations=evals or [],
        documents=body.documents or 0,
        links=body.links or 0,
        notes=body.notes or "",
        live=store.last_run_live,          # from the actual run, not the request body (#8)
        engine=store.last_run_detail,
    )
    return {k: v for k, v in rec.items() if k != "evaluations"}


@app.get("/api/runs/{run_id}")
def get_run(run_id: str) -> dict:
    """A single saved run WITH its evaluations (for re-opening a past run)."""
    rec = run_store.get(run_id)
    if rec:
        return rec
    for r in _SEED_RUNS:
        if r["runId"] == run_id:
            return r
    return {}


@app.post("/api/runs/{run_id}/export")
def export_run(run_id: str) -> Response:
    """Export the latest evaluations as a CSV download."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["questionId", "question", "verdict", "grounded", "sourceGroundedness", "shortfalls", "finalSummary"])
    for e in store.last_evaluations:
        writer.writerow([
            e["questionId"], e["question"], e["verdict"], e["grounded"],
            e["sourceGroundedness"], "; ".join(e["shortfalls"]), e["finalSummary"],
        ])
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{run_id}.csv"'},
    )


@app.get("/api/health")
def health() -> dict:
    return {"ok": True}
