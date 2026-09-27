"""python -m proxybot – reads the settings from the environment and runs the bots that have a token."""

import asyncio
import logging

import aiohttp

from .bot import ProxyBot
from .config import Settings
from .feed import fetch_snapshot
from .telegram import TelegramBot

log = logging.getLogger("proxybot")
RESTART_AFTER = 60.0  # seconds before a bot that crashed is started again


async def supervised(name: str, start) -> None:
    """Keep one bot running on its own: if it crashes (a revoked token, Telegram or Discord down at boot), log it and
    start it again later – without taking the other bot in the same process down with it."""
    while True:
        try:
            await start()
            return
        except asyncio.CancelledError:
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


async def run(settings: Settings) -> None:
    jobs = []
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30),
                                     headers={"User-Agent": "proxy-scraper-bot"}) as session:
        if settings.telegram_token:
            telegram = TelegramBot(settings.telegram_token, session)
            jobs += [supervised("telegram", telegram.run), keep_fresh(telegram, session, settings)]
        if settings.token:
            # a fresh client on every (re)start: a discord.Client that stopped can't be started again
            jobs.append(supervised("discord", lambda: ProxyBot(settings).start(settings.token)))
        await asyncio.gather(*jobs)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    asyncio.run(run(Settings.from_env()))


if __name__ == "__main__":
    main()
