"""What the bot has already posted, so a restart doesn't post the same run twice."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional


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

    def last_posted(self, guild_id: int) -> Optional[datetime]:
        try:
            return datetime.fromisoformat(self.posted[str(guild_id)])
        except (KeyError, ValueError):
            return None

    def is_due(self, guild_id: int, updated: datetime, every: timedelta) -> bool:
        """A new run, and the last post there is at least `every` old (the list runs hourly, the feed shouldn't)."""
        last = self.posted.get(str(guild_id))
        if last is None:
            return True
        try:
            posted = datetime.fromisoformat(last)
        except ValueError:
            return True
        # a few minutes of slack: scheduled runs don't start on the second
        return updated > posted and updated - posted >= every - timedelta(minutes=30)

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
