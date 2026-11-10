"""python -m proxybot – reads the settings from the environment and runs the bots that have a token."""

import asyncio
import contextlib
import logging
import os
import sys
from pathlib import Path
from typing import Iterable, Optional

import aiohttp
import discord

from .bot import ProxyBot
from .config import Settings
from .feed import fetch_snapshot
from .telegram import AuthFailed, TelegramBot

log = logging.getLogger("proxybot")
RESTART_AFTER = 60.0  # seconds before a bot that crashed is started again
# a token that is wrong or revoked: retrying can't help, and a bot that never logs in must not look like it runs
FATAL = (discord.LoginFailure, AuthFailed)


class Readiness:
    """Writes this process's PID to `path` once every configured bot has logged in.

    deploy/install.sh waits for that file to hold the PID systemd started, before it keeps a release: "the process
    is alive" is not enough, a bot that can't log in stays alive retrying."""

    def __init__(self, path: Optional[Path], bots: Iterable[str]):
        self.path = path
        self.waiting = set(bots)
        self.done = False
        if path is not None:
            with contextlib.suppress(FileNotFoundError):
                path.unlink()  # whatever an earlier process left there says nothing about this one

    def mark(self, name: str) -> None:
        self.waiting.discard(name)
        if self.waiting or self.done:
            return
        self.done = True
        log.info("ready: every bot is logged in")
        if self.path is not None:
            tmp = self.path.with_name(self.path.name + ".tmp")
            tmp.write_text(f"{os.getpid()}\n")
            os.replace(tmp, self.path)  # install.sh never reads a half-written file


async def supervised(name: str, start) -> None:
    """Keep one bot running on its own: if it crashes (Telegram or Discord down at boot), log it and start it again
    later – without taking the other bot in the same process down with it. A refused token is not retried: it ends
    the process (see FATAL)."""
    while True:
        try:
            await start()
            return
        except (asyncio.CancelledError, *FATAL):
            raise
        except Exception:  # noqa: BLE001 – anything that ends one bot must not end the other
            log.exception("%s stopped, starting it again in %.0f s", name, RESTART_AFTER)
        await asyncio.sleep(RESTART_AFTER)


async def keep_fresh(telegram: TelegramBot, session: aiohttp.ClientSession, settings: Settings) -> None:
    """The Telegram bot answers from memory – reload the list on the same schedule the Discord bot uses."""
    while True:
        try:
            telegram.snapshot = await fetch_snapshot(session, settings.feed_url)
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, KeyError, TypeError) as e:
            log.warning("could not load the list: %s", e)  # a half-deployed stats.json: keep the old one
        await asyncio.sleep(settings.poll_seconds)


def ready_file() -> Optional[Path]:
    path = os.environ.get("PROXYBOT_READY_FILE", "").strip()
    return Path(path) if path else None


async def run(settings: Settings, ready_path: Optional[Path] = None) -> None:
    bots = [name for name, token in (("telegram", settings.telegram_token), ("discord", settings.token)) if token]
    readiness = Readiness(ready_path, bots)
    jobs = []
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30),
                                     headers={"User-Agent": "proxy-scraper-bot"}) as session:
        if settings.telegram_token:
            telegram = TelegramBot(settings.telegram_token, session, ready=lambda: readiness.mark("telegram"))
            jobs += [supervised("telegram", telegram.run), keep_fresh(telegram, session, settings)]
        if settings.token:
            # a fresh client on every (re)start: a discord.Client that stopped can't be started again
            jobs.append(supervised("discord", lambda: ProxyBot(
                settings, ready=lambda: readiness.mark("discord")).start(settings.token)))
        await asyncio.gather(*jobs)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        asyncio.run(run(Settings.from_env(), ready_file()))
    except FATAL as e:
        log.error("giving up: %s", e)  # exit non-zero: systemd shows it as failed, the deploy rolls back
        sys.exit(2)


if __name__ == "__main__":
    main()
