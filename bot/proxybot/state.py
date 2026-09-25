"""What the bot has already posted, so a restart doesn't post the same run twice."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Dict


class State:
    def __init__(self, path: Path):
        self.path = path
        self.posted: Dict[str, str] = {}  # guild id -> run id of the last run posted there
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return  # missing or broken: start fresh, the worst case is one repeated post
        if isinstance(data, dict) and isinstance(data.get("posted"), dict):
            self.posted = {str(k): str(v) for k, v in data["posted"].items()}

    def is_new(self, guild_id: int, run_id: str) -> bool:
        return self.posted.get(str(guild_id)) != run_id

    def mark(self, guild_id: int, run_id: str) -> None:
        self.posted[str(guild_id)] = run_id
        self.save()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # write to a temporary file first, then rename – a crash never leaves half a file
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".state-")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump({"posted": self.posted}, fh)
        os.replace(tmp, self.path)
