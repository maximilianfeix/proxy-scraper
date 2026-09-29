"""Remembers the last choice from the setup wizard (as command line arguments), and whether the
one-time star hint was shown."""

from __future__ import annotations

import json
import os
from typing import List, Mapping, Optional

from .paths import DATA_DIR, atomic_write

PREFERENCES_FILE = DATA_DIR / "preferences.json"
STAR_HINT_AFTER = 2  # runs with hits before the hint – the first run is for trying it out


def _load() -> dict:
    try:
        data = json.loads(PREFERENCES_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _save(data: dict) -> None:
    atomic_write(PREFERENCES_FILE, json.dumps(data, indent=1))


def load_last_argv() -> Optional[List[str]]:
    argv = _load().get("last")
    if isinstance(argv, list) and all(isinstance(a, str) for a in argv):
        return argv
    return None


def save_last_argv(argv: List[str]) -> None:
    data = _load()
    data["last"] = argv
    _save(data)


def star_hint_due(env: Mapping[str, str] = os.environ) -> bool:
    """Counts a run that found proxies; True exactly once, on run STAR_HINT_AFTER.
    Never in CI or with PROXY_SCRAPER_NO_STAR_HINT set."""
    if env.get("PROXY_SCRAPER_NO_STAR_HINT") or env.get("CI"):
        return False
    data = _load()
    if data.get("star_hint_shown"):
        return False
    runs = data.get("runs_with_hits")
    runs = (runs if isinstance(runs, int) else 0) + 1
    data["runs_with_hits"] = runs
    due = runs >= STAR_HINT_AFTER
    if due:
        data["star_hint_shown"] = True
    try:
        _save(data)
    except OSError:
        return False  # can't remember it – better never than every time
    return due
