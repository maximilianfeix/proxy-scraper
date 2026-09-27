"""Which big sites let a proxy through – checked for the live list after every run.

Getting through to httpbin says little about Google or Reddit: both block most free proxies, but each in its own
way (Google redirects to a captcha page, Reddit answers 403, Amazon shows its bot check with a 202). A plain
"2xx/3xx = reachable" like --target would count Google's captcha redirect as a success, so every site here
has its own verdict. Only clear answers are kept: a timeout says nothing about whether the site blocks the proxy.

    python -m proxyscraper.sites results/<run>      # adds "sites": {"google": true, ...} to proxies.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import socket
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable, Dict, List, Optional, Tuple

from .netio import USER_AGENT
from .paths import atomic_write

TIMEOUT = 10.0
CONCURRENCY = 300


@dataclass(frozen=True)
class Site:
    name: str
    host: str
    path: str
    ok: Tuple[int, ...]                 # these statuses mean: the page came through
    blocked: Tuple[int, ...]            # these mean: the site turned the proxy away
    blocked_redirect: str = ""          # a redirect to a URL containing this is a block too (a captcha page)
    ok_redirect: str = ""               # ... and one containing this is fine (a consent screen)
    min_body: int = 0                   # an "ok" answer must come with at least this much page, else it's a stub
    title: str = ""                     # for people: "Google"

    def verdict(self, status: int, location: str = "", body: Optional[int] = None) -> Optional[bool]:
        """True = got through, False = blocked, None = the answer says neither. body: bytes of page read after
        the head (only needed with min_body)."""
        if status in self.ok:
            return not self.min_body or (body or 0) >= self.min_body
        if status in self.blocked:
            return False
        if 300 <= status < 400:
            if self.blocked_redirect and self.blocked_redirect in location:
                return False
            if self.ok_redirect and self.ok_redirect in location:
                return True
        return None


SITES = (
    Site("google", "www.google.com", "/search?q=weather", ok=(200,), blocked=(429,),
         blocked_redirect="/sorry/", ok_redirect="consent.google.", title="Google"),
    Site("reddit", "www.reddit.com", "/", ok=(200,), blocked=(403, 429), title="Reddit"),
    # Amazon answers bots with a 2-4 KB stub or captcha page, and since 2026-09 with status 200 on the home page
    # too – even without a proxy. The search tells them apart: real results are well over 100 KB.
    Site("amazon", "www.amazon.com", "/s?k=usb+cable", ok=(200,), blocked=(202, 503), min_body=32_000,
         title="Amazon"),
    # measured on 60 live proxies (2026-09-27): most get Instagram's login wall, a few the real profile page;
    # TikTok gives some a 403 or a small stub. ChatGPT, eBay and Indeed block everyone (the last two even without
    # a proxy) and LinkedIn and Twitch let everyone through – those say nothing, so they're not in here.
    Site("instagram", "www.instagram.com", "/instagram/", ok=(200,), blocked=(429,), blocked_redirect="accounts/login",
         min_body=30_000, title="Instagram"),
    Site("tiktok", "www.tiktok.com", "/@tiktok", ok=(200,), blocked=(403, 429), min_body=30_000, title="TikTok"),
)
SITE = {s.name: s for s in SITES}

Probe = Callable[[dict, Site, str], Awaitable[Optional[bool]]]


def parse_head(head: bytes) -> Tuple[int, str]:
    """Status code and Location header of a response head; (0, "") if it isn't HTTP."""
    lines = head.split(b"\r\n")
    parts = lines[0].split()
    if len(parts) < 2 or not parts[0].startswith(b"HTTP/") or not parts[1].isdigit():
        return 0, ""
    location = ""
    for line in lines[1:]:
        name, _, value = line.partition(b":")
        if name.strip().lower() == b"location":
            location = value.strip().decode("latin-1")
    return int(parts[1]), location


PAGE_TIME = 10.0  # extra seconds to read the page behind a 200 (min_body), on top of the normal timeout


def probe_timeout(site: Site, timeout: float) -> float:
    return timeout + (PAGE_TIME if site.min_body else 0)


def page_complete(head: bytes, body: int, tail: bytes) -> bool:
    """Did the whole (short) page arrive, or did the proxy hang up halfway? Only a complete short page is a stub –
    a cut-off one says nothing."""
    headers = {}
    for line in head.split(b"\r\n")[1:]:
        name, sep, value = line.partition(b":")
        if sep:
            headers[name.strip().lower()] = value.strip().lower()
    encodings = [e.strip() for e in headers.get(b"transfer-encoding", b"").split(b",")]
    if encodings[-1] == b"chunked":  # takes precedence over Content-Length
        return tail.endswith(b"0\r\n\r\n")
    length = headers.get(b"content-length", b"")
    if length:
        return length.isdigit() and body >= int(length)
    return True  # no length at all: the end of the connection is the end of the page


def real_probe(timeout: float = TIMEOUT) -> Probe:
    """Tunnel to the site through the proxy with verified TLS, send a browser-like GET, judge the answer."""
    from .checker import Checker

    checker = Checker(judge_ip="127.0.0.1", own_ips=(), timeout=timeout, connect_timeout=timeout / 2)

    async def probe(row: dict, site: Site, ip: str) -> Optional[bool]:
        async def go() -> Optional[bool]:
            opened = await checker._tls_tunnel(row["ptype"], row["proxy"], site.host, socket.inet_aton(ip), 443)
            if opened is None:
                return None
            reader, writer = opened
            try:
                writer.write(f"GET {site.path} HTTP/1.1\r\nHost: {site.host}\r\nUser-Agent: {USER_AGENT}\r\n"
                             "Accept: text/html,application/xhtml+xml,*/*;q=0.8\r\nAccept-Language: en-US,en;q=0.8\r\n"
                             "Connection: close\r\n\r\n".encode())
                await writer.drain()
                head = await reader.readuntil(b"\r\n\r\n")
                status, location = parse_head(head)
                body, tail = 0, b""
                if site.min_body and status in site.ok:  # read just enough to tell a page from a stub
                    while body < site.min_body:
                        chunk = await reader.read(16384)
                        if not chunk:
                            break
                        body += len(chunk)
                        tail = (tail + chunk)[-16:]
                    if body < site.min_body and not page_complete(head, body, tail):
                        return None  # cut off halfway: neither a page nor a stub
            finally:
                writer.close()
            return site.verdict(status, location, body)
        try:
            return await asyncio.wait_for(go(), probe_timeout(site, timeout))
        except (OSError, asyncio.TimeoutError, asyncio.IncompleteReadError, asyncio.LimitOverrunError, ValueError):
            return None
    return probe


def _resolve(host: str) -> str:
    return socket.getaddrinfo(host, 443, family=socket.AF_INET)[0][4][0]


async def fill_run(run_dir: Path, probe: Optional[Probe] = None, resolve: Callable[[str], str] = _resolve,
                   concurrency: int = CONCURRENCY) -> Dict[str, int]:
    """Probe every HTTPS-capable proxy of a run against every site; writes "sites" into its proxies.json.
    Returns how many proxies got through to each site."""
    probe = probe or real_probe()
    path = run_dir / "proxies.json"
    rows: List[dict] = json.loads(path.read_text(encoding="utf-8"))
    ips = {}
    for site in SITES:
        try:
            ips[site.name] = resolve(site.host)
        except OSError:
            continue  # this site can't be looked up right now – the others still can
    slots = asyncio.Semaphore(concurrency)

    async def one(row: dict, site: Site) -> None:
        async with slots:
            verdict = await probe(row, site, ips[site.name])
        if verdict is not None:
            row["sites"][site.name] = verdict

    jobs = []
    for row in rows:
        row["sites"] = {}
        if row.get("https") is True:
            jobs += [one(row, site) for site in SITES if site.name in ips]
    await asyncio.gather(*jobs)
    for row in rows:  # always in the same order, whichever answer came first
        row["sites"] = {s.name: row["sites"][s.name] for s in SITES if s.name in row["sites"]}
    # in one go: if the step gets killed (it has a timeout), the publish step still finds the old file intact
    atomic_write(path, json.dumps(rows, indent=1, ensure_ascii=False))
    return {s.name: sum(1 for r in rows if r["sites"].get(s.name)) for s in SITES}


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="check which big sites let the proxies of a run through")
    p.add_argument("run_dir", type=Path)
    p.add_argument("--timeout", type=float, default=TIMEOUT)
    args = p.parse_args(argv)
    counts = asyncio.run(fill_run(args.run_dir, real_probe(args.timeout)))
    print("got through: " + ", ".join(f"{name} {n}" for name, n in counts.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
