"""The Discord client: watches the live list and posts every new run, answers slash commands."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Literal, Optional

import aiohttp
import discord
from discord import app_commands
from discord.ext import tasks

from . import layout, messages
from .config import Settings
from .feed import TYPES, Snapshot, parse_snapshot, pick_one, select
from .state import State

log = logging.getLogger(__name__)

LOGO_FILE = Path(__file__).with_name("logo.png")
TypeChoice = Literal["any", "http", "socks4", "socks5"]


class ProxyBot(discord.Client):
    def __init__(self, settings: Settings):
        # no privileged intents needed: the bot only posts and answers slash commands
        super().__init__(intents=discord.Intents.default())
        self.settings = settings
        self.tree = app_commands.CommandTree(self)
        self.state = State(settings.state_file)
        self.snapshot: Optional[Snapshot] = None
        self.http_session: Optional[aiohttp.ClientSession] = None
        self._post_lock = asyncio.Lock()
        self._prepared: set = set()  # guild ids set up in this process (on_ready fires again after reconnects)
        self._layout_done = asyncio.Event()
        register_commands(self)

    async def setup_hook(self) -> None:
        self.http_session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30),
                                                  headers={"User-Agent": "proxy-scraper-discord-bot"})
        self.watch.change_interval(seconds=self.settings.poll_seconds)
        self.watch.start()

    async def close(self) -> None:
        self.watch.cancel()
        if self.http_session:
            await self.http_session.close()
        await super().close()

    async def on_ready(self) -> None:
        log.info("logged in as %s, in %d server(s)", self.user, len(self.guilds))
        if self.user and self.user.avatar is None and LOGO_FILE.exists():
            try:
                await self.user.edit(avatar=LOGO_FILE.read_bytes())
            except discord.HTTPException as e:  # avatar changes are rate limited – not worth failing over
                log.warning("could not set the avatar: %s", e)
        for guild in self.guilds:
            if guild.id not in self._prepared:
                await self.prepare_guild(guild)
        self._layout_done.set()

    async def on_guild_join(self, guild: discord.Guild) -> None:
        log.info("joined %s", guild.name)
        await self.prepare_guild(guild)

    async def prepare_guild(self, guild: discord.Guild) -> None:
        """Channels, commands and – if there is one – the latest run, right away."""
        try:
            await layout.ensure_layout(guild, LOGO_FILE.read_bytes() if LOGO_FILE.exists() else None)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)  # per server: shows up instantly instead of after up to an hour
        except discord.Forbidden:
            log.error("%s: missing permissions – re-invite the bot with the link from bot/README.md", guild.name)
            return
        self._prepared.add(guild.id)
        if self.snapshot:
            await self.post_run(guild, self.snapshot)

    # ------------------------------------------------------------------ watching the live list

    @tasks.loop(seconds=300)
    async def watch(self) -> None:
        try:
            snap = await self.fetch()
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, KeyError) as e:
            log.warning("live list not reachable: %s", e)
            return
        self.snapshot = snap
        for guild in self.guilds:
            await self.post_run(guild, snap)

    @watch.before_loop
    async def before_watch(self) -> None:
        await self.wait_until_ready()
        await self._layout_done.wait()  # channels first, otherwise the first run has nowhere to go

    async def fetch(self) -> Snapshot:
        base = self.settings.feed_url
        assert self.http_session is not None

        async def get(name: str):
            async with self.http_session.get(f"{base}/{name}") as response:
                response.raise_for_status()
                return await response.json(content_type=None)

        stats, rows = await asyncio.gather(get("stats.json"), get("proxies.json"))
        try:
            history = await get("history.json")
        except (aiohttp.ClientError, ValueError):
            history = []  # only needed for the trend
        return parse_snapshot(stats, rows, history if isinstance(history, list) else [])

    async def post_run(self, guild: discord.Guild, snap: Snapshot) -> None:
        async with self._post_lock:  # the watch loop and a new server joining could meet here
            if not self.state.is_new(guild.id, snap.run_id):
                return
            channels = {c.name: c for c in guild.text_channels if c.category and c.category.name == layout.CATEGORY}
            if "live-feed" not in channels:
                return  # layout not ready (missing permissions) – try again next time
            try:
                await channels["live-feed"].send(embed=messages.summary(snap),
                                                 file=messages.text_file(snap.proxies, "all.txt"))
                for ptype in TYPES:
                    channel = channels.get(ptype)
                    if channel is None:
                        continue
                    await layout.clear_own_messages(channel, guild.me)
                    of_type = [p for p in snap.proxies if p.ptype == ptype]
                    await channel.send(embed=messages.type_post(snap, ptype),
                                       file=messages.text_file(of_type, f"{ptype}.txt"))
            except discord.HTTPException as e:
                log.error("%s: posting failed: %s", guild.name, e)
                return
            self.state.mark(guild.id, snap.run_id)
            log.info("%s: posted run %s (%d proxies)", guild.name, snap.run_id, len(snap.proxies))


def register_commands(bot: ProxyBot) -> None:
    tree = bot.tree

    async def current(interaction: discord.Interaction) -> Optional[Snapshot]:
        if bot.snapshot is None:
            await interaction.response.send_message("The live list isn't loaded yet – try again in a minute.",
                                                    ephemeral=True)
        return bot.snapshot

    @tree.command(name="proxies", description="Working proxies from the last run, filtered and fastest first")
    @app_commands.describe(type="protocol", country="two-letter country code, e.g. DE or US",
                           https="only proxies that tunnel HTTPS", elite="only elite anonymity",
                           no_datacenter="skip exits in datacenters", count="how many to show (1–25)")
    async def proxies(interaction: discord.Interaction, type: TypeChoice = "any", country: str = "",
                      https: bool = False, elite: bool = False, no_datacenter: bool = False,
                      count: app_commands.Range[int, 1, 25] = 10) -> None:
        snap = await current(interaction)
        if snap is None:
            return
        ptype = "" if type == "any" else type
        matches = select(snap.proxies, ptype, country, https, elite, no_datacenter)
        criteria = ", ".join(x for x in (ptype, country.upper(), "HTTPS" if https else "", "elite" if elite else "",
                                         "no datacenter" if no_datacenter else "") if x) or "none"
        kwargs = {}
        if len(matches) > count:
            kwargs["file"] = messages.text_file(matches, "proxies.txt")
        await interaction.response.send_message(embed=messages.results(matches, count, criteria), ephemeral=True,
                                                **kwargs)

    @tree.command(name="proxy", description="One fast working proxy to try right now")
    @app_commands.describe(type="protocol", https="only proxies that tunnel HTTPS")
    async def proxy(interaction: discord.Interaction, type: TypeChoice = "any", https: bool = False) -> None:
        snap = await current(interaction)
        if snap is None:
            return
        pick = pick_one(select(snap.proxies, "" if type == "any" else type, https=https))
        await interaction.response.send_message(embed=messages.single(pick), ephemeral=True)

    @tree.command(name="stats", description="Numbers of the last run")
    async def stats(interaction: discord.Interaction) -> None:
        snap = await current(interaction)
        if snap is not None:
            await interaction.response.send_message(embed=messages.stats(snap), ephemeral=True)

    @tree.command(name="about", description="What this bot does")
    async def about(interaction: discord.Interaction) -> None:
        await interaction.response.send_message(embed=messages.about(), ephemeral=True)
