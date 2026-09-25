"""Remembers the last choice from the setup wizard (as command line arguments)."""

from __future__ import annotations

import json
from typing import List, Optional

from .paths import DATA_DIR, atomic_write

PREFERENCES_FILE = DATA_DIR / "preferences.json"


def load_last_argv() -> Optional[List[str]]:
    try:
        argv = json.loads(PREFERENCES_FILE.read_text(encoding="utf-8")).get("last")
    except (OSError, ValueError, AttributeError):
        return None
    if isinstance(argv, list) and all(isinstance(a, str) for a in argv):
        return argv
    return None


def save_last_argv(argv: List[str]) -> None:
    atomic_write(PREFERENCES_FILE, json.dumps({"last": argv}, indent=1))
