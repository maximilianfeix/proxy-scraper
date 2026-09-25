"""Settings from environment variables (on the server: /etc/proxybot.env, written by the deploy workflow)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

SITE = "https://maximilianfeix.github.io/proxy-scraper"
REPO = "https://github.com/maximilianfeix/proxy-scraper"


@dataclass(frozen=True)
class Settings:
    token: str
    feed_url: str = SITE
    state_file: Path = Path("state.json")
    poll_seconds: int = 300

    @classmethod
    def from_env(cls) -> "Settings":
        token = os.environ.get("DISCORD_TOKEN", "").strip()
        if not token:
            raise SystemExit("DISCORD_TOKEN is not set")
        return cls(
            token=token,
            feed_url=os.environ.get("PROXYBOT_FEED_URL", SITE).rstrip("/"),
            state_file=Path(os.environ.get("PROXYBOT_STATE", "state.json")),
            poll_seconds=max(60, int(os.environ.get("PROXYBOT_POLL_SECONDS", "300"))),
        )
