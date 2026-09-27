"""The Telegram bot: answers /proxy, /proxies and /stats from the live list.

Telegram's Bot API is plain HTTPS, so there's no extra library – aiohttp comes with discord.py anyway. The bot
long-polls getUpdates (no public address or webhook needed) and refreshes the list on its own schedule.
Everything that decides what to answer is in plain functions below, testable without a token.
"""

from __future__ import annotations

import asyncio
import html
import logging
import random
import re
from typing import Dict, List, Optional, Tuple

import aiohttp

from .config import REPO, SITE
from .feed import TYPES, Snapshot, pick_one, select

log = logging.getLogger(__name__)

API = "https://api.telegram.org/bot{token}/{method}"
MAX_LIST = 20          # more than this reads badly in a chat – the website has the rest
DEFAULT_LIST = 10
_COMMAND_RE = re.compile(r"^/([a-z]+)(?:@(\w+))?(?:\s+(.*))?$", re.I | re.S)
COMMANDS = ("proxy", "proxies", "stats", "help", "start")

HELP = f"""<b>Working free proxies, checked every hour</b>

/proxy – one fast proxy to try, with a curl line
/proxy de socks5 – from a country, of a type
/proxies 10 us https – a short list, fastest first
/stats – numbers of the last run

Filters in any order: a country code (de, us, …), a type (http, socks4, socks5), <code>https</code> and a number.
Everything else: <a href="{SITE}/">the website</a> · <a href="{REPO}">GitHub</a>"""


def parse_command(text: str, me: str = "") -> Optional[Tuple[str, List[str]]]:
    """'/proxies@ProxyScraperBot 5 us' -> ('proxies', ['5', 'us']). None for anything that isn't one of our
    commands, or is addressed to another bot (/help@OtherBot) – in a group, those aren't for us to answer."""
    m = _COMMAND_RE.match((text or "").strip())
    if not m or m[1].lower() not in COMMANDS:
        return None
    if m[2] and me and m[2].lower() != me.lower():
        return None
    return m[1].lower(), (m[3] or "").split()


def parse_filters(words: List[str]) -> Optional[Dict]:
    """Free words -> filters. None if a word means nothing, so the answer can explain instead of guessing."""
    out: Dict = {"country": "", "ptype": "", "https": False, "count": DEFAULT_LIST}
    for word in (w.lower() for w in words):
        if word in TYPES:
            out["ptype"] = word
        elif word == "https":
            out["https"] = True
        elif re.fullmatch(r"[0-9]+", word):  # not str.isdigit(): "²" passes that, int() can't read it
            out["count"] = max(1, min(MAX_LIST, int(word)))
        elif re.fullmatch(r"[a-z]{2}", word):
            out["country"] = word.upper()
        else:
            return None
    return out


def _proxy_line(proxy) -> str:
    extras = [proxy.country, f"{proxy.latency:,} ms", "HTTPS" if proxy.https else ""]
    return f"<code>{html.escape(proxy.url)}</code> {html.escape(' · '.join(e for e in extras if e))}"


def reply(command: str, words: List[str], snap: Optional[Snapshot], rng: Optional[random.Random] = None) -> str:
    """The answer to one command, as Telegram HTML."""
    if command in ("proxy", "proxies", "stats") and snap is None:
        return "The list is not loaded yet – try again in a minute."
    if command == "stats":
        s = snap.stats
        by_type = ", ".join(f"{s.get('by_type', {}).get(t, 0):,} {t}" for t in TYPES)
        return (f"<b>{s.get('total', len(snap.proxies)):,} working proxies</b> in the last run ({by_type}).\n"
                f"{s.get('https', 0):,} tunnel HTTPS, median latency {s.get('median_latency', 0):,} ms.\n"
                f"<a href=\"{SITE}/report/\">The week in numbers</a>")
    if command not in ("proxy", "proxies"):
        return HELP
    filters = parse_filters(words)
    if filters is None:
        return f"I didn't get <code>{html.escape(' '.join(words))}</code>.\n\n{HELP}"
    matches = select(snap.proxies, ptype=filters["ptype"], country=filters["country"], https=filters["https"])
    if not matches:
        return ("No proxy in the last run matches that. Try fewer filters, e.g. just /proxy, "
                f"or look at the <a href=\"{SITE}/\">full list</a>.")
    if command == "proxy":
        proxy = pick_one(matches, rng)
        scheme = "socks5h" if proxy.ptype == "socks5" else proxy.ptype  # DNS through the proxy too
        target = "https://api.ipify.org" if proxy.https else "http://api.ipify.org"
        curl = f"curl -x {scheme}://{html.escape(proxy.address)} {target}"
        return (f"{_proxy_line(proxy)}\n\nTry it:\n<code>{curl}</code>\n"
                "Free proxies come and go – if it doesn't answer, just ask again.")
    shown = matches[:filters["count"]]
    rest = len(matches) - len(shown)
    more = f"\n\n{rest:,} more on the <a href=\"{SITE}/\">website</a>." if rest else ""
    return "\n".join(_proxy_line(p) for p in shown) + more


class TelegramBot:
    """Long-polls for messages and answers them. `snapshot` is shared with whatever keeps the list fresh."""

    def __init__(self, token: str, session: aiohttp.ClientSession):
        self.token = token
        self.session = session
        self.snapshot: Optional[Snapshot] = None
        self.offset = 0
        self.me = ""  # our username, to ignore commands addressed to other bots

    async def call(self, method: str, **params):
        async with self.session.post(API.format(token=self.token, method=method), json=params,
                                     timeout=aiohttp.ClientTimeout(total=70)) as response:
            data = await response.json(content_type=None)
        if not data.get("ok"):
            raise RuntimeError(f"{method}: {data.get('description', 'failed')}")
        return data["result"]

    async def handle(self, update: dict) -> None:
        message = update.get("message") or {}
        parsed = parse_command(message.get("text", ""), self.me)
        chat = (message.get("chat") or {}).get("id")
        if parsed is None or chat is None:
            return  # not a command: stay quiet in groups
        await self.call("sendMessage", chat_id=chat, text=reply(*parsed, self.snapshot), parse_mode="HTML",
                        disable_web_page_preview=True)

    async def run(self) -> None:
        self.me = (await self.call("getMe")).get("username", "")
        await self.call("setMyCommands", commands=[
            {"command": "proxy", "description": "one fast proxy to try"},
            {"command": "proxies", "description": "a short list, fastest first"},
            {"command": "stats", "description": "numbers of the last run"},
            {"command": "help", "description": "how to use the filters"}])
        while True:
            try:
                updates = await self.call("getUpdates", offset=self.offset, timeout=50, allowed_updates=["message"])
            except (aiohttp.ClientError, asyncio.TimeoutError, RuntimeError, ValueError) as e:
                log.warning("telegram: %s", e)
                await asyncio.sleep(10)
                continue
            for update in updates:
                self.offset = max(self.offset, update.get("update_id", 0) + 1)
                try:
                    await self.handle(update)
                except (aiohttp.ClientError, asyncio.TimeoutError, RuntimeError, ValueError) as e:
                    log.warning("telegram: could not answer: %s", e)
