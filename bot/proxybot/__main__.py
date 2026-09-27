"""python -m proxybot – reads the settings from the environment and runs the bots that have a token."""

import asyncio
import logging

import aiohttp

from .bot import ProxyBot
from .config import Settings
from .feed import fetch_snapshot
from .telegram import TelegramBot

log = logging.getLogger("proxybot")


async def keep_fresh(telegram: TelegramBot, session: aiohttp.ClientSession, settings: Settings) -> None:
    """The Telegram bot answers from memory – reload the list on the same schedule the Discord bot uses."""
    while True:
        try:
            telegram.snapshot = await fetch_snapshot(session, settings.feed_url)
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as e:
            log.warning("could not load the list: %s", e)
        await asyncio.sleep(settings.poll_seconds)


async def run(settings: Settings) -> None:
    jobs = []
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30),
                                     headers={"User-Agent": "proxy-scraper-bot"}) as session:
        if settings.telegram_token:
            telegram = TelegramBot(settings.telegram_token, session)
            jobs += [telegram.run(), keep_fresh(telegram, session, settings)]
        if settings.token:
            discord_bot = ProxyBot(settings)
            jobs.append(discord_bot.start(settings.token))
        await asyncio.gather(*jobs)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    asyncio.run(run(Settings.from_env()))


if __name__ == "__main__":
    main()
