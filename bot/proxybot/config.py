"""Settings from environment variables (on the server: /etc/proxybot.env, written by the deploy workflow)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

SITE = "https://maximilianfeix.github.io/proxy-scraper"
REPO = "https://github.com/maximilianfeix/proxy-scraper"


@dataclass(frozen=True)
class Settings:
    token: str                     # Discord – empty when only the Telegram bot runs
    feed_url: str = SITE
    telegram_token: str = ""
    state_file: Path = Path("state.json")
    poll_seconds: int = 300
    post_every_hours: float = 6  # the list runs every hour – a summary in #live-feed at most this often

    @classmethod
    def from_env(cls) -> "Settings":
        token = os.environ.get("DISCORD_TOKEN", "").strip()
        telegram = os.environ.get("TELEGRAM_TOKEN", "").strip()
        if not token and not telegram:
            raise SystemExit("neither DISCORD_TOKEN nor TELEGRAM_TOKEN is set")
        return cls(
            token=token,
            telegram_token=telegram,
            feed_url=os.environ.get("PROXYBOT_FEED_URL", SITE).rstrip("/"),
            state_file=Path(os.environ.get("PROXYBOT_STATE", "state.json")),
            poll_seconds=max(60, int(os.environ.get("PROXYBOT_POLL_SECONDS", "300"))),
            post_every_hours=max(0.0, float(os.environ.get("PROXYBOT_POST_EVERY_HOURS", "6"))),
        )
