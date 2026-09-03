"""Evidence provenance + immutable store + template/export (G10).

Every ``AssuranceRecord`` is versioned, timestamped, attributable, and retained. The ``AssuranceStore``
is **write-once**: a record id can never be overwritten (the audit trail is immutable), mirroring the
S3-primary + local-JSONL pattern of ``api/run_store.py`` but self-contained here. ``governance_template``
renders the export form (Atlas stripe, per-dimension metric/band/threshold rows, auto L×I, evidence
fields, disposition, reviewers, attestation).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from ..contracts import AssuranceRecord
from ..logging_config import get_logger

log = get_logger("layer_c.evidence")


class ImmutableViolation(RuntimeError):
    """Raised on any attempt to overwrite an existing (immutable) assurance record."""


class AssuranceStore:
    """Append-only, write-once store of AssuranceRecords keyed by ``record_id``.

    Local JSONL is the durable mirror; an S3 bucket (if supplied) is written write-once too. A record
    whose id already exists is rejected — evidence is immutable (G10).
    """

    def __init__(self, path: Optional[Path] = None, *, bucket: str = "", prefix: str = "aah/assurance",
                 region: str = ""):
        self._path = Path(path) if path else None
        self._bucket, self._prefix, self._region = bucket, prefix.strip("/"), region
        self._ids: set[str] = set()
        self._client = None
        self._client_built = False
        if self._path and self._path.exists():
            for line in self._path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    self._ids.add(json.loads(line).get("record_id", ""))
                except ValueError:
                    continue

    # --- S3 (optional, write-once) -------------------------------------------------
    def _s3(self):
        if not self._bucket:
            return None
        if self._client_built:
            return self._client
        self._client_built = True
        try:
            import boto3

            self._client = boto3.client("s3", region_name=self._region) if self._region else boto3.client("s3")
        except Exception as exc:  # noqa: BLE001
            log.warning("S3 unavailable for assurance store (%s); local only", exc)
            self._client = None
        return self._client

    def _key(self, record_id: str) -> str:
        return f"{self._prefix}/{record_id}.json"

    # --- write-once put ------------------------------------------------------------
    def put(self, record: AssuranceRecord) -> str:
        rid = record.record_id
        if not rid:
            raise ValueError("AssuranceRecord has no record_id; cannot store immutably")
        if rid in self._ids:
            raise ImmutableViolation(f"assurance record {rid!r} already exists — records are immutable")
        self._ids.add(rid)
        if self._path:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as f:
                f.write(record.model_dump_json() + "\n")
        client = self._s3()
        if client is not None:
            try:
                client.put_object(Bucket=self._bucket, Key=self._key(rid),
                                  Body=record.model_dump_json().encode("utf-8"),
                                  ContentType="application/json")
            except Exception as exc:  # noqa: BLE001
                log.error("S3 put failed for %s (%s); kept local copy", rid, exc)
        log.info("stored assurance record %s (retention %s)", rid, record.retention_until)
        return rid

    def exists(self, record_id: str) -> bool:
        return record_id in self._ids


def governance_template(record: AssuranceRecord) -> dict:
    """Render the governance export form for one record (G10)."""
    return {
        "use_case": record.use_case,
        "atlas_stripe": record.atlas_stripe,
        "control_objective": record.control_objective,
        "schema_version": record.schema_version,
        "produced_at": record.produced_at,
        "retention_until": record.retention_until,
        "risk_policy_version": record.risk_policy_version,
        "dimensions": [
            {
                "dimension": a.dimension.value,
                "dim_id": a.dim_id,
                "metric_id": a.metric_id,
                "metric_value": a.metric_value,
                "band": a.band.value if a.band else None,
                "likelihood": a.likelihood,
                "impact": a.impact,
                "risk": a.risk,
                "trend": a.trend.value,
                "anchors": a.anchors,
            }
            for a in record.dimensions
        ],
        "aggregate_risk": {"max": record.aggregate_risk.max, "mean": record.aggregate_risk.mean},
        "disposition": record.disposition.value if record.disposition else None,
        "kri_alerts": [{"dimension": k.dimension.value, "kri": k.kri, "message": k.message,
                        "reevaluate": k.reevaluate, "sla_hours": k.sla_hours} for k in record.kri_alerts],
        "evidence_links": [{"url": e.url, "type": e.type, "description": e.description}
                           for e in record.evidence_links],
        "reviewers": [{"id": r.id, "lod": r.lod.value, "timestamp": r.timestamp}
                      for r in record.reviewers],
        "attestation": record.attestation,
        "coverage_scope": {"in_scope": record.coverage_scope.in_scope,
                           "out_of_scope": record.coverage_scope.out_of_scope,
                           "rationale": record.coverage_scope.rationale},
    }
