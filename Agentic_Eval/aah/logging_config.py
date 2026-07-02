"""Central logging setup for the harness (library, API server, and CLI).

One place configures the ``aah`` logger tree so every module gets consistent, timestamped
output to the console (stderr) and a rotating audit file at ``logs/aah.log``. Level is read
from the ``AAH_LOG_LEVEL`` env var (default ``INFO``).

Usage:
    from .logging_config import get_logger
    log = get_logger("api.server")     # -> logger "aah.api.server"
    log.info("started")

The CLI keeps its human-readable output on stdout via ``get_cli_logger()`` (a plain-format
logger) so terminal UX is unchanged while the same lines are also captured in the audit file.
"""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_LOG_DIR = _PROJECT_ROOT / "logs"
_LOG_FILE = _LOG_DIR / "aah.log"

_FMT = logging.Formatter(
    "%(asctime)s %(levelname)-7s %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
)

_configured = False
_file_handler: RotatingFileHandler | None = None


def _make_file_handler() -> RotatingFileHandler | None:
    """Rotating file handler for the audit trail; None if the log dir can't be created."""
    global _file_handler
    if _file_handler is not None:
        return _file_handler
    try:
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
        h = RotatingFileHandler(
            _LOG_FILE, maxBytes=2_000_000, backupCount=5, encoding="utf-8"
        )
        h.setFormatter(_FMT)
        _file_handler = h
    except OSError:
        _file_handler = None  # console logging still works
    return _file_handler


def setup_logging(*, force: bool = False) -> None:
    """Configure the ``aah`` logger once: console (stderr) + rotating file."""
    global _configured
    if _configured and not force:
        return

    level = os.environ.get("AAH_LOG_LEVEL", "INFO").upper()
    logger = logging.getLogger("aah")
    logger.setLevel(level)
    logger.handlers.clear()

    console = logging.StreamHandler(sys.stderr)
    console.setFormatter(_FMT)
    logger.addHandler(console)

    fh = _make_file_handler()
    if fh is not None:
        logger.addHandler(fh)

    logger.propagate = False  # don't double-log through the root logger
    _configured = True


def get_logger(name: str) -> logging.Logger:
    """Return a namespaced logger under ``aah`` (configuring logging on first use)."""
    setup_logging()
    full = name if name.startswith("aah") else f"aah.{name}"
    return logging.getLogger(full)


def get_cli_logger() -> logging.Logger:
    """A logger for CLI output: plain lines to stdout, also captured in the audit file.

    Kept off the ``aah`` console (stderr) handler so terminal output isn't duplicated, while
    still writing to ``logs/aah.log`` for the record.
    """
    setup_logging()
    log = logging.getLogger("aah.cli.out")
    if not getattr(log, "_cli_ready", False):
        stdout = logging.StreamHandler(sys.stdout)
        stdout.setFormatter(logging.Formatter("%(message)s"))
        log.addHandler(stdout)
        fh = _make_file_handler()
        if fh is not None:
            log.addHandler(fh)  # timestamped copy in the audit file
        log.setLevel(logging.INFO)
        log.propagate = False
        log._cli_ready = True  # type: ignore[attr-defined]
    return log
