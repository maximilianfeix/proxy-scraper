"""What the MCP server does, without the MCP SDK: the live list, filters, fresh checks and fetching pages.

Kept free of the SDK on purpose – the SDK needs Python 3.10+, this module runs (and is tested) wherever
proxy-scraper runs. mcp_server.py only turns these functions into MCP tools.
"""

from __future__ import annotations

import asyncio
import http.client
import ipaddress
import json
import secrets
import time
import urllib.error
import urllib.request
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Awaitable, Callable, Iterable, List, Optional, Sequence, Union
from urllib.parse import urlsplit

from .api import find_proxies_async
from .checker import CheckResult
from .netio import http_get
from .parsing import PROXY_TYPES
from .server import ProxyPool, RotatingServer

LIVE_BASES = ("https://maximilianfeix.github.io/proxy-scraper",
              "https://raw.githubusercontent.com/maximilianfeix/proxy-scraper/proxy-list")
CACHE_SECONDS = 300.0  # the list changes once an hour – no need to load 1 MB for every question
MAX_PAGE_BYTES = 2_000_000
FETCH_ROUNDS = 2  # a download that breaks off mid-way is tried once more, through another proxy
FETCH_ATTEMPTS = 8  # proxies per page before giving up – more than --serve's 3, an agent can't just press reload
USER_AGENT = "Mozilla/5.0 (compatible; proxy-scraper; +https://github.com/maximilianfeix/proxy-scraper)"
PROTOCOLS = ("any", *PROXY_TYPES)


class AgentError(Exception):
    """Something the agent can act on – the message says what to do instead."""


class _BrokeOff(Exception):
    """The proxy dropped the connection in the middle of the page."""


# --------------------------------------------------------------------------- the live list

@dataclass
class LiveList:
    rows: List[dict]
    stats: dict
    loaded_at: float

    @property
    def updated(self) -> str:
        return str(self.stats.get("updated", ""))

    @property
    def run_hours(self) -> int:
        hours = self.stats.get("run_hours")
        return hours if isinstance(hours, int) and hours > 0 else 6  # lists from before run_hours ran every 6 h

    def age_minutes(self, now: Optional[datetime] = None) -> Optional[int]:
        try:
            updated = datetime.fromisoformat(self.updated)
        except ValueError:
            return None
        return max(0, round(((now or datetime.now(timezone.utc)) - updated).total_seconds() / 60))


Fetch = Callable[..., Awaitable[bytes]]


class LiveSource:
    """The hourly list from GitHub Pages, cached for a few minutes. A failed refresh keeps the old list."""

    def __init__(self, fetch: Fetch = http_get, clock: Callable[[], float] = time.monotonic,
                 ttl: float = CACHE_SECONDS, bases: Sequence[str] = LIVE_BASES):
        self.fetch, self.clock, self.ttl, self.bases = fetch, clock, ttl, bases
        self._cache: Optional[LiveList] = None
        self._lock: Optional[asyncio.Lock] = None

    async def get(self) -> LiveList:
        if self._cache and self.clock() - self._cache.loaded_at < self.ttl:
            return self._cache
        if self._lock is None:  # created here: before Python 3.10 a lock is bound to the event loop
            self._lock = asyncio.Lock()
        async with self._lock:  # several tools at once shouldn't load the list several times
            if self._cache and self.clock() - self._cache.loaded_at < self.ttl:
                return self._cache
            error: Optional[Exception] = None
            for base in self.bases:
                try:
                    rows, stats = await asyncio.gather(self._json(f"{base}/proxies.json"),
                                                       self._json(f"{base}/stats.json"))
                except Exception as e:  # try the next mirror
                    error = e
                    continue
                if isinstance(rows, list) and isinstance(stats, dict):
                    self._cache = LiveList([r for r in rows if isinstance(r, dict)], stats, self.clock())
                    return self._cache
            if self._cache:
                return self._cache
            raise AgentError(f"The live proxy list couldn't be loaded ({error}). check_proxies can still find "
                             "working proxies by checking them from this machine.")

    async def _json(self, url: str):
        return json.loads(await self.fetch(url, timeout=20))


# --------------------------------------------------------------------------- filtering

def _check_protocol(protocol: str) -> str:
    protocol = (protocol or "any").lower()
    if protocol not in PROTOCOLS:
        raise AgentError(f"protocol must be one of {', '.join(PROTOCOLS)}, not {protocol!r}")
    return protocol


def normalize_countries(countries: Iterable[str]) -> List[str]:
    out = []
    for c in countries or ():
        code = str(c).strip().upper()
        if len(code) != 2 or not code.isalpha():
            raise AgentError(f"Countries are two-letter codes like DE, US or JP, not {c!r}.")
        out.append(code)
    return list(dict.fromkeys(out))


def select(rows: Iterable[dict], protocol: str = "any", countries: Iterable[str] = (), https_only: bool = False,
           elite_only: bool = False, exclude_datacenter: bool = False, exclude_blocklisted: bool = False,
           stable_only: bool = False, max_latency_ms: int = 0, run_hours: int = 1) -> List[dict]:
    """The rows that pass every filter, fastest first – the same filters as on the website."""
    protocol = _check_protocol(protocol)
    wanted = set(normalize_countries(countries))
    stable_runs = -(-24 // max(run_hours, 1))  # runs in a row that make a day
    out = [r for r in rows
           if (protocol == "any" or r.get("ptype") == protocol)
           and (not wanted or r.get("country") in wanted)
           and (not https_only or r.get("https") is True)
           and (not elite_only or r.get("anonymity") == "elite")
           and (not exclude_datacenter or not r.get("hosting"))
           and (not exclude_blocklisted or not r.get("blocklisted"))
           and (not stable_only or (r.get("streak") or 0) >= stable_runs)
           and (not max_latency_ms or (r.get("latency") or 0) <= max_latency_ms)]
    return sorted(out, key=lambda r: r.get("latency") or 0)


def describe(item: Union[dict, CheckResult], run_hours: Optional[int] = None) -> dict:
    """One proxy the way an agent gets it: plain names, a ready-to-use URL."""
    if isinstance(item, CheckResult):
        item = {"ptype": item.ptype, "proxy": item.proxy, "country": item.country, "latency": item.latency,
                "https": item.https, "anonymity": item.anonymity, "org": item.org, "hosting": item.hosting,
                "blocklisted": item.blocklisted}
    streak = item.get("streak")
    return {
        "url": f"{item['ptype']}://{item['proxy']}",
        "protocol": item["ptype"],
        "address": item["proxy"],
        "country": item.get("country") or None,
        "latency_ms": item.get("latency"),
        "https": item.get("https"),
        "anonymity": item.get("anonymity") or None,
        "provider": item.get("org") or None,
        "datacenter": item.get("hosting"),
        "blocklisted": item.get("blocklisted"),
        "up_for_hours": streak * run_hours if streak and run_hours else None,
    }


def shortage_note(rows: Sequence[dict], wanted: int, matched: int, countries: Iterable[str] = ()) -> Optional[str]:
    """When fewer proxies match than asked for: say so, and where there are more."""
    if matched >= wanted:
        return None
    note = f"Only {matched} proxy matches" if matched == 1 else f"Only {matched} proxies match"
    note += " the filters right now – loosen them for more, or use check_proxies to test from this machine."
    if list(countries):
        top = Counter(r.get("country") for r in rows if r.get("country")).most_common(8)
        note += " Countries with the most proxies: " + ", ".join(f"{c} ({n})" for c, n in top) + "."
    return note


# --------------------------------------------------------------------------- fresh checks

Progress = Callable[[float, str], Awaitable[None]]


async def check_fresh(want: int = 10, protocol: str = "any", countries: Iterable[str] = (), https_only: bool = False,
                      elite_only: bool = False, exclude_datacenter: bool = False, exclude_blocklisted: bool = False,
                      max_latency_ms: int = 0, mode: str = "live", progress: Optional[Progress] = None,
                      tick: float = 5.0) -> List[dict]:
    """Check proxies from this machine: the live list again ("live", ~30–90 s) or all 700+ sources ("full").
    While it runs, `progress` hears from us every `tick` seconds – that keeps clients from timing out."""
    protocol = _check_protocol(protocol)
    if mode not in ("live", "full"):
        raise AgentError(f"mode must be 'live' or 'full', not {mode!r}")
    task = asyncio.ensure_future(find_proxies_async(
        types=list(PROXY_TYPES) if protocol == "any" else [protocol], want=want, https=https_only,
        countries=normalize_countries(countries), anonymity="elite" if elite_only else "",
        max_latency=max_latency_ms, no_datacenter=exclude_datacenter, no_blocklisted=exclude_blocklisted,
        concurrency=500, verbose=False, _recheck="live" if mode == "live" else None))
    started = time.monotonic()
    try:
        while not task.done():
            await asyncio.wait({task}, timeout=tick)
            if progress and not task.done():
                elapsed = time.monotonic() - started
                await progress(elapsed, f"checking proxies from this machine … {elapsed:.0f} s")
        return [describe(r) for r in task.result()]
    finally:
        if not task.done():
            task.cancel()


# --------------------------------------------------------------------------- fetching pages

def check_target(url: str) -> str:
    """Only http(s) to public hosts. localhost or private ranges would mean the proxy operator's own network."""
    parts = urlsplit(url.strip())
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise AgentError(f"Give a full http:// or https:// URL, e.g. https://example.com – not {url!r}.")
    host = parts.hostname
    if host == "localhost" or host.endswith(".localhost"):
        raise AgentError(f"{host} is this machine – fetch it directly, not through a public proxy.")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return url.strip()
    if not ip.is_global:
        raise AgentError(f"{host} is a private or reserved address – free proxies are on the public internet.")
    return url.strip()


_SKIP = {"script", "style", "noscript", "svg", "template", "iframe", "canvas"}
_BLOCK = {"p", "div", "br", "li", "tr", "title", "h1", "h2", "h3", "h4", "h5", "h6", "section", "article", "ul",
          "ol", "table", "header", "footer", "nav", "main", "aside", "blockquote", "pre", "dt", "dd", "figcaption",
          "hr", "form", "details", "summary"}


class _TextParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: List[str] = []
        self.skipping = 0

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP:
            self.skipping += 1
        elif tag in _BLOCK:
            self.parts.append("\n")

    def handle_startendtag(self, tag, attrs):
        if tag in _BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in _SKIP:
            self.skipping = max(0, self.skipping - 1)
        elif tag in _BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skipping:
            self.parts.append(data)


def html_to_text(html: str) -> str:
    """Readable text from HTML: no scripts or styles, one line per block, whitespace collapsed."""
    parser = _TextParser()
    parser.feed(html)
    parser.close()
    lines = (" ".join(line.split()) for line in "".join(parser.parts).split("\n"))
    return "\n".join(line for line in lines if line)


def _as_result(r: dict) -> Optional[CheckResult]:
    try:
        return CheckResult(f"{r['ptype']} {r['proxy']}", r["ptype"], r["proxy"], int(r.get("latency") or 0),
                           str(r.get("exit_ip") or ""), https=r.get("https"), anonymity=r.get("anonymity") or "",
                           country=r.get("country") or "", asn=int(r.get("asn") or 0), org=r.get("org") or "",
                           hosting=r.get("hosting"), blocklisted=r.get("blocklisted"))
    except (KeyError, TypeError, ValueError):
        return None


_TEXT_TYPES = ("text/", "json", "xml", "javascript", "x-www-form-urlencoded")


def _read_all(response) -> bytes:
    """The body, or _BrokeOff if the connection ended early. read(n) doesn't complain when a Content-Length
    body comes up short – it just returns less – so the remaining length is checked by hand."""
    try:
        body = response.read(MAX_PAGE_BYTES + 1)
    except http.client.IncompleteRead:
        raise _BrokeOff() from None
    remaining = getattr(response, "length", None)
    if remaining and len(body) <= MAX_PAGE_BYTES:
        raise _BrokeOff()
    return body


class PageFetcher:
    """Loads pages through the rotating server of this package, running on 127.0.0.1 with a random password:
    the same failover as `--serve`, and HTTPS only through proxies that passed the verified-TLS test."""

    def __init__(self, source: LiveSource, allow_private: bool = False, timeout: float = 20.0,
                 strategy: str = "weighted"):
        self.source, self.allow_private, self.timeout, self.strategy = source, allow_private, timeout, strategy
        self.server: Optional[RotatingServer] = None
        self._password = secrets.token_urlsafe(24)
        self._loaded_at: Optional[float] = None

    async def _ready(self) -> LiveList:
        live = await self.source.get()
        results = [r for r in (_as_result(row) for row in live.rows) if r]
        if self.server is None:
            self.server = RotatingServer(ProxyPool(results, strategy=self.strategy), host="127.0.0.1", port=0,
                                         timeout=min(self.timeout, 10.0), password=self._password,
                                         max_attempts=FETCH_ATTEMPTS)
            await self.server.start()
        elif live.loaded_at != self._loaded_at:
            self.server.pool.merge(results)  # a new hour's list: new proxies in, dead ones out, counters kept
        self._loaded_at = live.loaded_at
        return live

    async def fetch(self, url: str, protocol: str = "any", country: str = "", max_chars: int = 20000,
                    raw_html: bool = False) -> dict:
        if self.allow_private:
            parts = urlsplit(url)
            if parts.scheme not in ("http", "https") or not parts.hostname:
                raise AgentError(f"Give a full http:// or https:// URL, not {url!r}.")
        else:
            url = check_target(url)
        protocol = _check_protocol(protocol)
        countries = normalize_countries([country] if country else [])
        live = await self._ready()
        tls = urlsplit(url).scheme == "https"
        usable = select(live.rows, protocol=protocol, countries=countries, https_only=tls,
                        run_hours=live.run_hours)
        if not usable:
            what = " ".join(x for x in (countries[0] if countries else "", "" if protocol == "any" else protocol,
                                        "HTTPS-capable" if tls else "") if x)
            raise AgentError(f"No {what} proxy in the live list right now."
                             + (shortage_note(live.rows, 1, 0, countries) or ""))
        session = secrets.token_hex(6)
        wishes = [f"country-{countries[0].lower()}"] if countries else []
        if protocol != "any":
            wishes.append(f"type-{protocol}")
        started = time.monotonic()
        for round_ in range(FETCH_ROUNDS):
            # the same wishes a user would put in the proxy login; session names are letters and digits only
            user = "-".join([*wishes, f"session-{session}r{round_}"])
            proxy = f"http://{user}:{self._password}@127.0.0.1:{self.server.port}"
            try:
                status, final_url, headers, body = await asyncio.to_thread(self._get, url, proxy)
                break
            except _BrokeOff:
                continue  # a new session name: the next round starts with a different proxy
        else:
            raise AgentError(f"The download of {url} broke off {FETCH_ROUNDS} times – free proxies sometimes drop "
                             "long transfers. Try again, or ask for less (a smaller page, max_chars doesn't help "
                             "here since the whole page is loaded).")
        held = self.server.pool.session_entry(f"{session}r{round_}")
        content_type = headers.get("Content-Type", "") if headers else ""
        is_text = not content_type or any(t in content_type.lower() for t in _TEXT_TYPES)
        text = ""
        if is_text:
            charset = headers.get_content_charset() if headers else None
            text = body.decode(charset or "utf-8", "replace")
            if not raw_html and "html" in content_type.lower():
                text = html_to_text(text)
        truncated = len(text) > max_chars or len(body) > MAX_PAGE_BYTES
        return {
            "url": url,
            "final_url": final_url,
            "status": status,
            "content_type": content_type or None,
            "via": held.result.url if held else None,
            "proxy_country": (held.result.country or None) if held else None,
            "elapsed_ms": round((time.monotonic() - started) * 1000),
            "bytes": min(len(body), MAX_PAGE_BYTES),
            "text": text[:max_chars] if is_text else "",
            "truncated": truncated,
            "note": None if is_text else f"Binary content ({content_type}) isn't returned as text.",
        }

    def _get(self, url: str, proxy: str):
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
        try:
            with opener.open(request, timeout=self.timeout * 3) as response:
                return response.status, response.url, response.headers, _read_all(response)
        except urllib.error.HTTPError as e:
            if e.headers.get("X-Proxy-Scraper") != "no-proxy-answered":
                return e.code, e.url, e.headers, _read_all(e)  # 403, 404 … still the target's answer
            reason = f"none of {FETCH_ATTEMPTS} proxies got through"
        except (urllib.error.URLError, OSError, http.client.HTTPException) as e:
            reason = str(getattr(e, "reason", e))
            if "502" in reason:  # the rotating server's answer to CONNECT when no proxy got through
                reason = f"none of {FETCH_ATTEMPTS} proxies got through"
        raise AgentError(f"Couldn't load {url}: {reason}. Some sites block known public proxies (Wikipedia, for "
                         "example); otherwise free proxies simply come and go – try again, other proxies get "
                         "picked, or use check_proxies for fresh ones.")

    async def close(self) -> None:
        if self.server is not None:
            await self.server.close()
            self.server = None
