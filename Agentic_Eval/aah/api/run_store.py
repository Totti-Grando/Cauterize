"""Persistent store for saved evaluation runs (the Run History audit trail).

Storage backend (chosen in Settings → Long-term storage):

* **S3 (primary)** — when ``s3.enabled`` + a bucket are configured, each run is written as a
  JSON object at ``s3://<bucket>/<prefix>/runs/<runId>.json``. Listing/reading pull from S3, so
  history is durable and survives the box entirely. AWS credentials come from the ``aws`` section
  via ``config_store.apply_to_env()`` — the same chain Bedrock uses.
* **Local JSONL (cache/fallback)** — every run is ALSO mirrored to ``aah/api/runs.jsonl`` so the
  app keeps working offline and there's a local copy. When S3 is disabled this is the only store.

The boto3 client is built lazily (first use, after creds are applied) and any S3 error is logged
and degrades gracefully to the local cache rather than crashing a request.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from ..logging_config import get_logger
from .config_store import store as config_store

log = get_logger("api.run_store")

_RUNS_PATH = Path(__file__).resolve().parent / "runs.jsonl"


def _summarize(evaluations: list[dict]) -> dict[str, int]:
    tally = {"correct": 0, "partial": 0, "incorrect": 0, "unverifiable": 0}
    for e in evaluations:
        v = e.get("verdict")
        if v in tally:
            tally[v] += 1
    return tally


class RunStore:
    def __init__(self, path: Path = _RUNS_PATH):
        self._path = path
        self._runs: list[dict] = []
        self._known: set[str] = set()
        self._client = None            # lazily built boto3 S3 client
        self._client_built = False
        self._hydrated = False         # whether we've pulled the S3 index at least once
        self.load()

    # --- local cache --------------------------------------------------------------
    def load(self) -> None:
        """Load the local JSONL cache into memory (offline copy / fallback)."""
        self._runs = []
        self._known = set()
        if self._path.exists():
            for line in self._path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                self._runs.append(rec)
                if rec.get("runId"):
                    self._known.add(rec["runId"])
        if self._runs:
            log.info("loaded %d runs from local cache", len(self._runs))

    def _append_local(self, rec: dict) -> None:
        with self._path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")

    # --- S3 backend ---------------------------------------------------------------
    def _s3_conf(self) -> Optional[tuple[str, str]]:
        """Return (bucket, prefix) if S3 is enabled+configured, else None."""
        s3 = config_store.s3 or {}
        if not s3.get("enabled") or not s3.get("bucket"):
            return None
        return s3["bucket"], (s3.get("prefix") or "aah").strip("/")

    def _s3(self):
        """Lazily build (and cache) the boto3 S3 client; None if unavailable."""
        if self._client_built:
            return self._client
        self._client_built = True
        try:
            import boto3  # resolves creds from env (config_store.apply_to_env)

            region = (config_store.s3.get("region") or config_store.aws.get("region") or None)
            self._client = boto3.client("s3", region_name=region) if region else boto3.client("s3")
            log.info("S3 client ready (region=%s)", region or "default")
        except Exception as exc:  # noqa: BLE001 - missing boto3 / creds / config
            log.warning("S3 unavailable (%s); using local cache only", exc)
            self._client = None
        return self._client

    def _key(self, prefix: str, run_id: str) -> str:
        return f"{prefix}/runs/{run_id}.json"

    def _put_s3(self, rec: dict) -> bool:
        conf = self._s3_conf()
        client = self._s3() if conf else None
        if not conf or client is None:
            return False
        bucket, prefix = conf
        try:
            client.put_object(
                Bucket=bucket,
                Key=self._key(prefix, rec["runId"]),
                Body=json.dumps(rec).encode("utf-8"),
                ContentType="application/json",
            )
            log.info("run %s written to s3://%s/%s", rec["runId"], bucket, self._key(prefix, rec["runId"]))
            return True
        except Exception as exc:  # noqa: BLE001
            log.error("S3 put failed for %s (%s); kept local copy", rec.get("runId"), exc)
            return False

    def _sync_from_s3(self) -> None:
        """Pull any runs present in S3 but not yet in memory (S3 is the source of truth)."""
        conf = self._s3_conf()
        client = self._s3() if conf else None
        if not conf or client is None:
            return
        bucket, prefix = conf
        base = f"{prefix}/runs/"
        try:
            paginator = client.get_paginator("list_objects_v2")
            fetched = 0
            for page in paginator.paginate(Bucket=bucket, Prefix=base):
                for obj in page.get("Contents", []):
                    run_id = Path(obj["Key"]).stem
                    if not run_id or run_id in self._known:
                        continue
                    body = client.get_object(Bucket=bucket, Key=obj["Key"])["Body"].read()
                    rec = json.loads(body)
                    self._runs.append(rec)
                    self._known.add(rec.get("runId", run_id))
                    fetched += 1
            self._hydrated = True
            if fetched:
                log.info("synced %d runs from s3://%s/%s", fetched, bucket, base)
        except Exception as exc:  # noqa: BLE001
            log.error("S3 sync failed (%s); serving local cache", exc)

    # --- public API ---------------------------------------------------------------
    def add(
        self,
        *,
        mode: str,
        provider: str,
        primary_model: str,
        evaluations: list[dict],
        documents: int = 0,
        links: int = 0,
        user: str = "local",
        notes: str = "",
        live: bool = False,
        engine: str = "",
    ) -> dict[str, Any]:
        stamp = datetime.now()
        source = "live" if live else "fixture"
        rec = {
            "runId": "RUN-" + stamp.strftime("%Y%m%d-%H%M%S"),
            "date": stamp.strftime("%Y-%m-%d %H:%M"),
            "user": user,
            "documents": documents,
            "links": links,
            "primaryModel": primary_model,
            "provider": provider,
            "mode": mode,
            "questions": len(evaluations),
            "verdictSummary": _summarize(evaluations),
            "exportStatus": "pending",
            # Provenance: whether these verdicts came from real model calls or offline fixtures.
            "source": source,
            "live": live,
            "engine": engine,
            "notes": notes or f"{mode} run · {len(evaluations)} questions · {source}",
            "evaluations": evaluations,
        }
        # Always keep a local copy (durable offline mirror); also push to S3 when it's primary.
        self._runs.append(rec)
        self._known.add(rec["runId"])
        self._append_local(rec)
        stored = self._put_s3(rec)
        log.info("saved run %s (%s, %d questions, s3=%s)", rec["runId"], source, len(evaluations), stored)
        return rec

    def list(self, include_evaluations: bool = False) -> list[dict]:
        """Saved runs, newest first (evaluations stripped unless requested)."""
        self._sync_from_s3()
        rows = sorted(self._runs, key=lambda r: r.get("runId", ""), reverse=True)
        if include_evaluations:
            return rows
        return [{k: v for k, v in r.items() if k != "evaluations"} for r in rows]

    def get(self, run_id: str) -> dict | None:
        for r in self._runs:
            if r.get("runId") == run_id:
                return r
        # Not cached — try S3 directly.
        conf = self._s3_conf()
        client = self._s3() if conf else None
        if conf and client is not None:
            bucket, prefix = conf
            try:
                body = client.get_object(Bucket=bucket, Key=self._key(prefix, run_id))["Body"].read()
                rec = json.loads(body)
                self._runs.append(rec)
                self._known.add(run_id)
                return rec
            except Exception as exc:  # noqa: BLE001 - not found / access error
                log.warning("S3 get failed for %s (%s)", run_id, exc)
        return None


store = RunStore()
