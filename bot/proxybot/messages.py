"""Everything the bot posts: embeds and file attachments, built from a Snapshot."""

from __future__ import annotations

import io
from typing import List, Optional, Sequence

import discord

from .config import REPO, SITE
from .feed import Proxy, Snapshot, as_lines, pct, table, top_countries

LIME = 0xD4F77A
LOGO = "https://raw.githubusercontent.com/maximilianfeix/proxy-scraper/main/docs/logo.png"
FOOTER = "Free proxies are run by strangers. Never send passwords or personal data through them."
TYPE_NAMES = {"http": "HTTP", "socks4": "SOCKS4", "socks5": "SOCKS5"}


def _embed(title: str, description: str = "", url: str = SITE) -> discord.Embed:
    embed = discord.Embed(title=title, description=description, url=url, color=LIME)
    embed.set_author(name="proxy-scraper", url=REPO, icon_url=LOGO)
    return embed


def text_file(proxies: Sequence[Proxy], name: str) -> discord.File:
    return discord.File(io.BytesIO(as_lines(proxies).encode()), filename=name)


def summary(snap: Snapshot) -> discord.Embed:
    """The post for #live-feed after every run."""
    st = snap.stats
    total = st.get("total", len(snap.proxies))
    previous = snap.previous_total()
    trend = ""
    if previous:
        diff = total - previous
        trend = f"  ({'+' if diff >= 0 else ''}{diff:,} since the last run)"
    by_type = st.get("by_type") or {}
    embed = _embed(f"{total:,} working proxies", f"Checked again just now.{trend}")
    embed.timestamp = snap.updated
    embed.add_field(name="HTTP", value=f"{by_type.get('http', 0):,}")
    embed.add_field(name="SOCKS4", value=f"{by_type.get('socks4', 0):,}")
    embed.add_field(name="SOCKS5", value=f"{by_type.get('socks5', 0):,}")
    embed.add_field(name="HTTPS", value=f"{st.get('https', 0):,} ({pct(st.get('https', 0), total)})")
    embed.add_field(name="Elite", value=f"{st.get('elite', 0):,} ({pct(st.get('elite', 0), total)})")
    median = st.get("median_latency")
    embed.add_field(name="Median latency", value=f"{median / 1000:.1f} s" if median else "–")
    countries = top_countries(st)
    if countries:
        embed.add_field(name="Top countries", value=" · ".join(countries), inline=False)
    embed.add_field(name="Fastest right now", value=f"```\n{table(snap.proxies, 10)}\n```", inline=False)
    embed.set_footer(text=FOOTER)
    return embed


def type_post(snap: Snapshot, ptype: str) -> discord.Embed:
    """The post for #http, #socks4 and #socks5: the fastest ones, the full list is attached."""
    of_type = [p for p in snap.proxies if p.ptype == ptype]
    https = sum(p.https for p in of_type)
    embed = _embed(f"{len(of_type):,} {TYPE_NAMES[ptype]} proxies",
                   f"{https:,} of them tunnel HTTPS. The complete list is attached, fastest first.")
    embed.timestamp = snap.updated
    embed.add_field(name="Fastest 15", value=f"```\n{table(of_type, 15)}\n```", inline=False)
    embed.set_footer(text=FOOTER)
    return embed


def results(matches: List[Proxy], count: int, criteria: str) -> discord.Embed:
    """Answer to /proxies."""
    if not matches:
        embed = _embed("No matching proxy", f"Nothing in the last run matches {criteria}. Try fewer filters.")
        return embed
    more = " The full list is attached." if len(matches) > count else ""
    # the table goes into the description: fields are capped at 1024 characters, descriptions at 4096
    return _embed(f"{len(matches):,} matching proxies",
                  f"Filter: {criteria}. Fastest first.{more}\n```\n{table(matches, count)}\n```")


def single(proxy: Optional[Proxy]) -> discord.Embed:
    """Answer to /proxy."""
    if proxy is None:
        return _embed("No proxy available", "The live list is empty right now. Try again after the next run.")
    embed = _embed(proxy.url, f"```\n{proxy.url}\n```")
    embed.add_field(name="Latency", value=f"{proxy.latency:,} ms")
    embed.add_field(name="Country", value=proxy.country or "–")
    embed.add_field(name="HTTPS", value="yes" if proxy.https else "no")
    if proxy.anonymity:
        embed.add_field(name="Anonymity", value=proxy.anonymity)
    if proxy.org:
        embed.add_field(name="Provider", value=proxy.org + (" (datacenter)" if proxy.hosting else ""), inline=False)
    if proxy.blocklisted is not None:
        embed.add_field(name="Blocklist", value="on SpamCop" if proxy.blocklisted else "not listed")
    scheme = "socks5h" if proxy.ptype == "socks5" else proxy.ptype
    embed.add_field(name="Try it", value=f"`curl -x {scheme}://{proxy.address} https://api.ipify.org`", inline=False)
    return embed


def stats(snap: Snapshot) -> discord.Embed:
    """Answer to /stats – the same numbers as the summary, without the list."""
    embed = summary(snap)
    embed.remove_field(len(embed.fields) - 1)
    return embed


def about() -> discord.Embed:
    """Pinned in #about and the answer to /about."""
    embed = _embed("What this server is", (
        "Every hour a GitHub Action collects public proxies from 700+ lists and checks every one of them: "
        "a real handshake, a honeypot check on two independent sites, a content check (nothing may be injected), "
        "then HTTPS, anonymity, country and provider. What passes ends up here.\n\n"
        f"**Browse and filter:** {SITE}\n**Run the checks yourself:** {REPO}"))
    embed.add_field(name="Channels", value=(
        "**#live-feed** a summary every 6 hours\n"
        "**#http**, **#socks4**, **#socks5** the current list per protocol, updated with every summary\n"
        "**#commands** ask the bot"), inline=False)
    embed.add_field(name="Commands", value=(
        "`/proxies` filter by type, country, HTTPS, elite, datacenter, blocklist\n"
        "`/proxy` one fast proxy to try\n"
        "`/stats` numbers of the last run\n"
        "`/about` this message"), inline=False)
    embed.set_footer(text=FOOTER)
    return embed
