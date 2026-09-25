"""The bot sets up its own corner of the server, so nothing has to be clicked by hand after inviting it.

Idempotent: existing channels are found by name and only fixed up, never duplicated.
"""

from __future__ import annotations

import contextlib
import logging
from dataclasses import dataclass
from typing import Dict, Optional

import discord

from . import messages

log = logging.getLogger(__name__)

CATEGORY = "proxy-scraper"


@dataclass(frozen=True)
class ChannelSpec:
    name: str
    topic: str
    read_only: bool = True  # only the bot posts here


CHANNELS = (
    ChannelSpec("about", "What this is and how to use it."),
    ChannelSpec("live-feed", "A summary after every run of the live proxy list (every 6 hours)."),
    ChannelSpec("http", "The current HTTP proxies, fastest first. Replaced after every run."),
    ChannelSpec("socks4", "The current SOCKS4 proxies, fastest first. Replaced after every run."),
    ChannelSpec("socks5", "The current SOCKS5 proxies, fastest first. Replaced after every run."),
    ChannelSpec("commands", "Ask the bot: /proxies, /proxy, /stats, /about", read_only=False),
)


async def ensure_layout(guild: discord.Guild, logo: Optional[bytes] = None) -> Dict[str, discord.TextChannel]:
    """Category + channels with topics and permissions; returns name -> channel."""
    me = guild.me
    category = discord.utils.get(guild.categories, name=CATEGORY)
    if category is None:
        category = await guild.create_category(CATEGORY, reason="proxy-scraper bot setup")
        log.info("%s: created category", guild.name)

    channels: Dict[str, discord.TextChannel] = {}
    for spec in CHANNELS:
        overwrites = {}
        if spec.read_only:
            # everyone can read and react, only the bot can write
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(send_messages=False, create_public_threads=False,
                                                                create_private_threads=False),
                me: discord.PermissionOverwrite(send_messages=True, embed_links=True, attach_files=True,
                                                manage_messages=True),
            }
        channel = discord.utils.get(category.text_channels, name=spec.name)
        if channel is None:
            channel = await guild.create_text_channel(spec.name, category=category, topic=spec.topic,
                                                      overwrites=overwrites, reason="proxy-scraper bot setup")
            log.info("%s: created #%s", guild.name, spec.name)
        elif channel.topic != spec.topic:
            await channel.edit(topic=spec.topic, reason="proxy-scraper bot setup")
        channels[spec.name] = channel

    await _pin_about(channels["about"], me)
    if logo and guild.icon is None and guild.me.guild_permissions.manage_guild:
        await guild.edit(icon=logo, reason="proxy-scraper bot setup")
    return channels


async def _pin_about(channel: discord.TextChannel, me: discord.Member) -> None:
    """Exactly one pinned about message from the bot; updated in place when the text changes."""
    embed = messages.about()
    async for message in channel.history(limit=20, oldest_first=True):
        if message.author == me and message.embeds and message.embeds[0].title == embed.title:
            if message.embeds[0].description != embed.description or \
                    [f.value for f in message.embeds[0].fields] != [f.value for f in embed.fields]:
                await message.edit(embed=embed)
            if not message.pinned:
                await message.pin()
            return
    message = await channel.send(embed=embed)
    await message.pin()


async def clear_own_messages(channel: discord.TextChannel, me: discord.Member) -> None:
    """Remove the bot's earlier lists in a per-protocol channel – old proxies are mostly dead anyway."""
    async for message in channel.history(limit=50):
        if message.author == me and not message.pinned:
            with contextlib.suppress(discord.NotFound):  # already gone
                await message.delete()
