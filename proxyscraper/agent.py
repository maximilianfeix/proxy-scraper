"""What the MCP server does, without the MCP SDK: the live list, filters, fresh checks and fetching pages.

Kept free of the SDK on purpose – the SDK needs Python 3.10+, this module runs (and is tested) wherever
proxy-scraper runs. mcp_server.py only turns these functions into MCP tools.
"""

from __future__ import annotations

import asyncio
import base64
import codecs
import contextlib
import http.client
import ipaddress
import json
import re
import secrets
import socket
import ssl
import threading
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Awaitable, Callable, Iterable, Iterator, List, Optional, Sequence, Union
from urllib.parse import quote, urljoin, urlsplit, urlunsplit

import certifi

from .api import find_proxies_async
from .checker import CheckResult
from .netio import http_get
from .pages import SITE_URL
from .parsing import PROXY_TYPES, make_key
from .publish import RAW_BASE
from .server import ProxyPool, RotatingServer

LIVE_BASES = (SITE_URL.rstrip("/"), RAW_BASE)  # GitHub Pages first, the raw branch as the mirror
CACHE_SECONDS = 300.0  # the list changes once an hour – no need to load 1 MB for every question
RETRY_AFTER = 60.0  # after a failed refresh: serve the old list this long before asking GitHub again
NEXT_RUN_GRACE = 300.0  # the hourly run takes a few minutes – look for the new list a bit after the hour
MAX_PAGE_BYTES = 2_000_000
MAX_REDIRECTS = 5
FETCH_ROUNDS = 3  # a proxy that breaks off or breaks TLS is retired, and the page is tried through another
FETCH_ATTEMPTS = 8  # proxies per page before giving up – more than --serve's 3, an agent can't just press reload
USER_AGENT = "Mozilla/5.0 (compatible; proxy-scraper; +https://github.com/maximilianfeix/proxy-scraper)"
PROTOCOLS = ("any", *PROXY_TYPES)


class AgentError(Exception):
    """Something the agent can act on – the message says what to do instead."""


class _ProxyFault(Exception):
    """The proxy that carried this request may have misbehaved (dropped the page, broke TLS) – try another.
    Only proven when another proxy then gets the page; if all fail the same way, it's the site."""

    def __init__(self, message: str, certificate: bool = False):
        super().__init__(message)
        self.certificate = certificate


class _NoProxy(AgentError):
    """The local server tried its proxies and none got through."""


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
                 ttl: float = CACHE_SECONDS, bases: Sequence[str] = LIVE_BASES,
                 wall: Callable[[], float] = time.time):
        self.fetch, self.clock, self.ttl, self.bases, self.wall = fetch, clock, ttl, bases, wall
        self._cache: Optional[LiveList] = None
        self._lock: Optional[asyncio.Lock] = None
        self._retry_at = 0.0
        self._expires = 0.0

    def _fresh_enough(self) -> bool:
        return bool(self._cache) and (self.clock() < self._expires or self.clock() < self._retry_at)

    def _keep_for(self, live: LiveList) -> float:
        """Seconds to keep this list: until the next run should have published a new one, at least ttl."""
        try:
            updated = datetime.fromisoformat(live.updated).timestamp()
        except ValueError:
            return self.ttl
        until_next = updated + live.run_hours * 3600 + NEXT_RUN_GRACE - self.wall()
        return max(self.ttl, min(until_next, live.run_hours * 3600))

    async def get(self) -> LiveList:
        if self._fresh_enough():
            return self._cache
        if self._lock is None:  # created here: before Python 3.10 a lock is bound to the event loop
            self._lock = asyncio.Lock()
        async with self._lock:  # several tools at once shouldn't load the list several times
            if self._fresh_enough():
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
                    self._expires = self.clock() + self._keep_for(self._cache)
                    return self._cache
            if self._cache:  # GitHub is unreachable: the old list, and don't wait for it again on every call
                self._retry_at = self.clock() + RETRY_AFTER
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
    return sorted(matching(rows, protocol, countries, https_only, elite_only, exclude_datacenter,
                           exclude_blocklisted, stable_only, max_latency_ms, run_hours),
                  key=lambda r: r.get("latency") or 0)


def matching(rows: Iterable[dict], protocol: str = "any", countries: Iterable[str] = (), https_only: bool = False,
             elite_only: bool = False, exclude_datacenter: bool = False, exclude_blocklisted: bool = False,
             stable_only: bool = False, max_latency_ms: int = 0, run_hours: int = 1) -> Iterator[dict]:
    """The rows that pass every filter, in list order – checks the filters before the first row is asked for."""
    protocol = _check_protocol(protocol)
    wanted = set(normalize_countries(countries))
    stable_runs = -(-24 // max(run_hours, 1))  # runs in a row that make a day
    return (r for r in rows
            if (protocol == "any" or r.get("ptype") == protocol)
           and (not wanted or r.get("country") in wanted)
           and (not https_only or r.get("https") is True)
           and (not elite_only or r.get("anonymity") == "elite")
           and (not exclude_datacenter or not r.get("hosting"))
           and (not exclude_blocklisted or not r.get("blocklisted"))
           and (not stable_only or (r.get("streak") or 0) >= stable_runs)
           and (not max_latency_ms or (r.get("latency") or 0) <= max_latency_ms))


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


async def _with_progress(awaitable, progress: Optional[Progress], tick: float, message: str):
    """Wait for `awaitable`, telling `progress` every `tick` seconds that we're still at it – MCP clients reset
    their timeouts on progress, so long checks and slow pages don't get cancelled."""
    task = asyncio.ensure_future(awaitable)
    started = time.monotonic()
    try:
        while not task.done():
            await asyncio.wait({task}, timeout=tick)
            if progress and not task.done():
                elapsed = time.monotonic() - started
                await progress(elapsed, f"{message} … {elapsed:.0f} s")
        return task.result()
    finally:
        if not task.done():
            task.cancel()


async def check_fresh(want: int = 10, protocol: str = "any", countries: Iterable[str] = (), https_only: bool = False,
                      elite_only: bool = False, exclude_datacenter: bool = False, exclude_blocklisted: bool = False,
                      max_latency_ms: int = 0, mode: str = "live", progress: Optional[Progress] = None,
                      tick: float = 5.0) -> List[dict]:
    """Check proxies from this machine: the live list again ("live", ~30–90 s) or all 700+ sources ("full").
    While it runs, `progress` hears from us every `tick` seconds – that keeps clients from timing out."""
    protocol = _check_protocol(protocol)
    if mode not in ("live", "full"):
        raise AgentError(f"mode must be 'live' or 'full', not {mode!r}")
    found = await _with_progress(find_proxies_async(
        types=list(PROXY_TYPES) if protocol == "any" else [protocol], want=want, https=https_only,
        countries=normalize_countries(countries), anonymity="elite" if elite_only else "",
        max_latency=max_latency_ms, no_datacenter=exclude_datacenter, no_blocklisted=exclude_blocklisted,
        concurrency=500, verbose=False, _recheck="live" if mode == "live" else None),
        progress, tick, "checking proxies from this machine")
    return [describe(r) for r in found]


# --------------------------------------------------------------------------- fetching pages

_NUMERIC_HOST = re.compile(r"[0-9a-fx.]+")  # 127.1, 2130706433, 0x7f000001: IPv4 in disguise


def check_scheme(url: str) -> str:
    """A well-formed http(s) URL with an ASCII host (bücher.de -> xn--bcher-kva.de) and a real port."""
    url = url.strip()
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname or any(c.isspace() for c in url):
        raise AgentError(f"Give a full http:// or https:// URL, e.g. https://example.com – not {url!r}.")
    if parts.username is not None:
        raise AgentError("URLs with a login (user:password@) aren't sent through public proxies – strangers run "
                         "them.")
    try:
        port = parts.port
        host = parts.hostname.encode("idna").decode("ascii") if not parts.hostname.isascii() else parts.hostname
    except (ValueError, UnicodeError):
        raise AgentError(f"{url!r} has an invalid host or port.") from None
    netloc = f"[{host}]" if ":" in host else host
    if port is not None:
        netloc += f":{port}"
    # the request line is ASCII: /wiki/München -> /wiki/M%C3%BCnchen, anything already encoded stays as it is
    path = quote(parts.path, safe="/%:@!$&'()*+,;=-._~")
    query = quote(parts.query, safe="=&%+/?:@!$'()*,;-._~")
    return urlunsplit((parts.scheme, netloc, path, query, ""))


def _is_public(ip) -> bool:
    if ip.version == 6 and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_global


def check_target(url: str) -> str:
    """Only http(s) to public hosts – runs for the first URL and for every redirect. Local names and private
    ranges would mean the proxy operator's own network (or, through a misconfigured proxy, yours)."""
    url = check_scheme(url)
    host = urlsplit(url).hostname.rstrip(".").lower()
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal", ".home.arpa")):
        raise AgentError(f"{host} is a local name – fetch it directly, not through a public proxy.")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        if not _NUMERIC_HOST.fullmatch(host):
            return _check_resolved(url, host)
        try:
            ip = ipaddress.IPv4Address(socket.inet_aton(host))
        except (OSError, ValueError):
            return _check_resolved(url, host)
    if not _is_public(ip):
        raise AgentError(f"{host} is a private or reserved address – free proxies are on the public internet.")
    return url


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


def _check_resolved(url: str, host: str) -> str:
    """A name like 127.0.0.1.nip.io or an intranet host is as private as its address. Looked up here because
    some upstreams (SOCKS4) resolve names on this machine. Unknown names pass – no proxy will reach them."""
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except (OSError, UnicodeError):
        return url
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0].split("%", 1)[0])
        except ValueError:
            continue
        if not _is_public(ip):
            raise AgentError(f"{host} resolves to {ip}, a private or reserved address – free proxies are on the "
                             "public internet.")
    return url


def next_hop(url: str, location: str, check: Callable[[str], str]) -> str:
    """Where a redirect leads – checked like the first URL, and never from https down to plain http."""
    # http.client hands header values over as latin-1 – UTF-8 locations come back readable this way
    with contextlib.suppress(UnicodeEncodeError, UnicodeDecodeError):
        location = location.encode("latin-1").decode("utf-8")
    target = urljoin(url, location)
    if urlsplit(url).scheme == "https" and urlsplit(target).scheme == "http":
        raise AgentError(f"{url} redirects to plain http ({target}). Not followed: that part would skip the "
                         "verified TLS. Fetch the http URL directly if you want it anyway.")
    return check(target)


def decode_body(body: bytes, charset: Optional[str]) -> str:
    """Text in the charset the server named – or UTF-8 when it named one Python doesn't know (utf8mb4 …)."""
    try:
        if not codecs.lookup(charset or "utf-8")._is_text_encoding:  # zlib, base64 … aren't charsets
            charset = "utf-8"
    except LookupError:
        charset = "utf-8"
    return body.decode(charset or "utf-8", "replace")


def _as_result(r: dict) -> Optional[CheckResult]:
    try:
        return CheckResult(make_key(r["ptype"], r["proxy"]), r["ptype"], r["proxy"], int(r.get("latency") or 0),
                           str(r.get("exit_ip") or ""), https=r.get("https"), anonymity=r.get("anonymity") or "",
                           country=r.get("country") or "", asn=int(r.get("asn") or 0), org=r.get("org") or "",
                           hosting=r.get("hosting"), blocklisted=r.get("blocklisted"))
    except (KeyError, TypeError, ValueError):
        return None


_TEXT_TYPES = ("text/", "json", "xml", "javascript", "x-www-form-urlencoded")
_TUNNEL_502 = re.compile(r"Tunnel connection failed: 502\b")  # http.client's words for our server's 502


def _read_all(response) -> bytes:
    """The body, or _ProxyFault if the connection ended early. read(n) doesn't complain when a Content-Length
    body comes up short – it just returns less – so the remaining length is checked by hand."""
    try:
        body = response.read(MAX_PAGE_BYTES + 1)
    except http.client.IncompleteRead:
        raise _ProxyFault("the proxy dropped the page halfway") from None
    remaining = getattr(response, "length", None)
    if remaining and len(body) <= MAX_PAGE_BYTES:
        raise _ProxyFault("the proxy dropped the page halfway")
    return body


def _to_text(body: bytes, headers, content_type: str, raw_html: bool) -> str:
    text = decode_body(body, headers.get_content_charset() if headers else None)
    return text if raw_html or "html" not in content_type.lower() else html_to_text(text)


class PageFetcher:
    """Loads pages through the rotating server of this package, running on 127.0.0.1 with a random password:
    the same failover as `--serve`, and HTTPS only through proxies that passed the verified-TLS test.

    Deliberately http.client and not urllib: urllib honours no_proxy and the system's proxy exceptions (on macOS
    *.local and 169.254/16), which would send such requests out directly from this machine."""

    def __init__(self, source: LiveSource, allow_private: bool = False, timeout: float = 20.0,
                 strategy: str = "weighted", check: Optional[Callable[[str], str]] = None):
        self.source, self.timeout, self.strategy = source, timeout, strategy
        self.check = check or (check_scheme if allow_private else check_target)  # for the URL and every redirect
        self.allows_private = allow_private
        self.server: Optional[RotatingServer] = None
        self._password = secrets.token_urlsafe(24)
        self._list_id: object = None
        self._lock: Optional[asyncio.Lock] = None
        self.downloads_running = 0  # threads inside _get right now (worker threads: counted under a lock)
        self._count_lock = threading.Lock()
        self._tls = ssl.create_default_context(cafile=certifi.where())
        per_attempt = min(timeout, 10.0)
        # the client waits for the server to work through its attempts (connect + first answer each)
        self._client_timeout = per_attempt * 2 * FETCH_ATTEMPTS + 10

    async def _ready(self) -> LiveList:
        live = await self.source.get()
        if self._lock is None:
            self._lock = asyncio.Lock()
        async with self._lock:  # parallel fetches: one starts the server, the others wait for it
            # the list is downloaded again every few minutes – only a new run's list may change the pool,
            # otherwise every proxy we retired would be back five minutes later
            list_id = live.updated or live.loaded_at
            if self.server is None or list_id != self._list_id:
                results = [r for r in (_as_result(row) for row in live.rows) if r]
                if self.server is None:
                    server = RotatingServer(ProxyPool(results, strategy=self.strategy, strict_tls=True),
                                            host="127.0.0.1", port=0, timeout=min(self.timeout, 10.0),
                                            password=self._password, max_attempts=FETCH_ATTEMPTS,
                                            public_targets_only=not self.allows_private)
                    await server.start()
                    self.server = server  # only once it listens
                else:
                    self.server.pool.merge(results, drop_missing=True)  # a new run's list is the whole truth
                self._list_id = list_id
        return live

    async def fetch(self, url: str, protocol: str = "any", country: str = "", max_chars: int = 20000,
                    raw_html: bool = False, progress: Optional[Progress] = None, tick: float = 5.0) -> dict:
        url = await asyncio.to_thread(self.check, url)  # may look the name up
        protocol = _check_protocol(protocol)
        countries = normalize_countries([country] if country else [])
        live = await self._ready()
        tls = urlsplit(url).scheme == "https"
        if not any(True for _ in matching(live.rows, protocol, countries, https_only=tls, run_hours=live.run_hours)):
            what = " ".join(x for x in (countries[0] if countries else "", "" if protocol == "any" else protocol,
                                        "HTTPS-capable" if tls else "") if x)
            raise AgentError(f"No {what} proxy in the live list right now."
                             + (shortage_note(live.rows, 1, 0, countries) or ""))
        session = secrets.token_hex(6)
        wishes = [f"country-{countries[0].lower()}"] if countries else []
        if protocol != "any":
            wishes.append(f"type-{protocol}")
        pool, port = self.server.pool, self.server.port
        started = time.monotonic()
        result, faults, suspects = None, [], []
        for round_ in range(FETCH_ROUNDS):
            # the same wishes a user would put in the proxy login; session names are letters and digits only
            name = f"{session}r{round_}"
            user = "-".join([*wishes, f"session-{name}"])
            try:
                result = await self._download(url, user, port, progress, tick)
                break
            except _ProxyFault as e:
                faults.append(e)
                bad = pool.session_entry(name)
                if bad and not bad.disabled:
                    pool.retire(bad)  # out while we retry, so the next round gets a different proxy
                    suspects.append(bad)
            except _NoProxy:
                if not faults:
                    raise
                break  # nobody left after the faults – below it's decided whose fault it was
        if result is None:
            for entry in suspects:
                pool.revive(entry)  # every proxy failed the same way: that's the site, not them
            if faults and all(f.certificate for f in faults):
                raise AgentError(f"The TLS certificate of {url} failed verification through {len(faults)} different "
                                 f"prox{'y' if len(faults) == 1 else 'ies'} ({faults[-1]}). The site's certificate is "
                                 "probably invalid or expired – nothing a proxy can fix.")
            raise AgentError(f"Couldn't load {url}: {faults[-1]}, and no other proxy got it through. Free proxies "
                             "come and go – try again in a moment.")
        # got it: the proxies that failed on the way are proven bad and stay out
        status, final_url, headers, body = result
        held = pool.session_entry(name)
        content_type = headers.get("Content-Type", "") if headers else ""
        is_text = not content_type or any(t in content_type.lower() for t in _TEXT_TYPES)
        # up to 2 MB of HTML: parse it off the event loop, which also runs the proxy server
        text = await asyncio.to_thread(_to_text, body, headers, content_type, raw_html) if is_text else ""
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

    async def _download(self, url: str, user: str, port: int, progress: Optional[Progress], tick: float):
        """_get in a thread. If the caller is cancelled, the socket is shut down so the thread ends too – a thread
        can't be cancelled, and it would otherwise wait for minutes on a proxy that doesn't answer."""
        slot: dict = {}
        try:
            return await _with_progress(asyncio.to_thread(self._get, url, user, port, slot), progress, tick,
                                        "loading the page through a proxy")
        except BaseException:  # cancelled, or the progress report failed because the client left
            conn = slot.get("conn")
            sock = conn.sock if conn is not None else None
            if sock is not None:
                with contextlib.suppress(OSError):
                    sock.shutdown(socket.SHUT_RDWR)  # wakes the reading thread on Unix
                with contextlib.suppress(OSError):
                    sock.close()  # and on Windows, where shutdown alone leaves the read waiting
            raise

    def _get(self, url: str, user: str, port: int, slot: dict):
        """GET through the local rotating server, following redirects by hand so every hop gets checked."""
        with self._count_lock:
            self.downloads_running += 1
        try:
            auth = "Basic " + base64.b64encode(f"{user}:{self._password}".encode()).decode()
            for _hop in range(MAX_REDIRECTS + 1):
                status, headers, body, location = self._get_once(url, auth, port, slot)
                if location is None:
                    return status, url, headers, body
                url = next_hop(url, location, self.check)  # a public page may point somewhere private
            raise AgentError(f"{url} redirected more than {MAX_REDIRECTS} times – stopped there.")
        finally:
            with self._count_lock:
                self.downloads_running -= 1

    def _get_once(self, url: str, auth: str, port: int, slot: dict):
        parts = urlsplit(url)
        https = parts.scheme == "https"
        headers = {"User-Agent": USER_AGENT, "Accept": "*/*", "Accept-Encoding": "identity"}
        if https:  # CONNECT through the server, then TLS end to end – verified against certifi's roots
            conn = http.client.HTTPSConnection("127.0.0.1", port, timeout=self._client_timeout, context=self._tls)
            conn.set_tunnel(parts.hostname, parts.port or 443, headers={"Proxy-Authorization": auth})
            target = urlunsplit(("", "", parts.path or "/", parts.query, ""))
        else:  # a classic proxy request with the absolute URL
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=self._client_timeout)
            headers["Proxy-Authorization"] = auth
            target = urlunsplit((parts.scheme, parts.netloc, parts.path or "/", parts.query, ""))
        slot["conn"] = conn
        try:
            conn.request("GET", target, headers=headers)
            response = conn.getresponse()
            if conn.sock is not None:  # the answer is there: the rest shouldn't take the failover's patience
                conn.sock.settimeout(min(self.timeout, 30.0))
            marker = response.getheader("X-Proxy-Scraper")
            if marker == "no-proxy-answered":
                raise _NoProxy(self._failed(url, f"none of {FETCH_ATTEMPTS} proxies got through"))
            if marker == "bad-request":
                raise AgentError(f"The request for {url} couldn't be passed on – an unusual URL?")
            location = response.getheader("Location")
            if response.status in (301, 302, 303, 307, 308) and location:
                return response.status, response.headers, b"", location  # the body isn't needed – not read at all
            return response.status, response.headers, _read_all(response), None
        except ssl.SSLCertVerificationError as e:
            raise _ProxyFault(f"certificate check failed: {e.verify_message}", certificate=True) from None
        except (ssl.SSLError, ConnectionResetError, http.client.RemoteDisconnected, http.client.IncompleteRead) as e:
            raise _ProxyFault(f"the proxy dropped the connection ({e.__class__.__name__})") from None
        except (OSError, http.client.HTTPException) as e:
            reason = str(e)
            if _TUNNEL_502.search(reason):  # the server's answer to CONNECT when no proxy got through
                raise _NoProxy(self._failed(url, f"none of {FETCH_ATTEMPTS} proxies got through")) from None
            raise AgentError(self._failed(url, reason)) from None
        finally:
            conn.close()

    @staticmethod
    def _failed(url: str, reason: str) -> str:
        return (f"Couldn't load {url}: {reason}. Some sites block known public proxies (Wikipedia, for example); "
                "otherwise free proxies simply come and go – try again, other proxies get picked, or use "
                "check_proxies for fresh ones.")

    async def close(self) -> None:
        if self.server is not None:
            await self.server.close()
            self.server = None
