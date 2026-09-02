"""Tiny dependency-free .env loader.

The provider/generator/scorer adapters read their keys from the environment
(``ANTHROPIC_API_KEY`` for Claude, ``GEMINI_API_KEY`` for the Gemini provider). This loads
a ``.env`` file into ``os.environ`` so you can drop keys in one place. ``.env`` is gitignored
— never commit real keys; ``.env.example`` is the template to copy.

Existing environment variables win by default (``override=False``), so a key exported in the
shell is not clobbered by the file.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Union


def _strip_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def load_dotenv(path: Union[str, Path] = ".env", *, override: bool = False) -> dict[str, str]:
    """Parse ``path`` and set the variables in ``os.environ``. Returns what was loaded.

    Format: ``KEY=VALUE`` per line. Blank lines and ``#`` comments are ignored; an optional
    leading ``export`` is allowed; values may be single- or double-quoted. A missing file is
    not an error (returns ``{}``) — keys can also come straight from the shell environment.
    """

    p = Path(path)
    loaded: dict[str, str] = {}
    if not p.exists():
        return loaded

    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        value = _strip_quotes(value)
        loaded[key] = value
        if override or key not in os.environ:
            os.environ[key] = value
    return loaded
