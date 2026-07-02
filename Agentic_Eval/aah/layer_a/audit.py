"""AuditRecord persistence (spec §5 step 7). Append-only JSONL: simple, diffable, replayable.

Each line is one fully self-describing AuditRecord including its WeightConfig, so any run
can be re-scored deterministically from the log alone (§7.6).
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

from ..contracts import AuditRecord


class AuditLog:
    """A JSONL sink/source for AuditRecords."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, record: AuditRecord) -> None:
        line = record.model_dump_json()
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    def read_all(self) -> list[AuditRecord]:
        return list(self.iter_records())

    def iter_records(self) -> Iterator[AuditRecord]:
        if not self.path.exists():
            return
        with self.path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    yield AuditRecord.model_validate_json(line)
