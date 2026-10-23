"""Is the exit IP on a spam blocklist? Sites that use such lists answer those proxies with captchas or not at all.

One DNS lookup per exit IP against SpamCop (bl.spamcop.net), cached for the run; parallel lookups of the
same IP share one query. Measured on the live
list: 29 % of exit IPs were listed there. DroneBL lists 59 % (it is essentially a list of open proxies),
too many to be useful as a filter, so it isn't used.

Some blocklist operators refuse queries coming from large public resolvers and answer every query then.
Before the run, the documented test address 127.0.0.2 is looked up: only if it comes back as listed and
a normal address doesn't, the answers are trusted. Otherwise every result stays unknown (None).
"""

from __future__ import annotations

import asyncio
import socket
from typing import Awaitable, Callable, Dict, Optional

ZONE = "bl.spamcop.net"
CONCURRENT_LOOKUPS = 50
LOOKUP_TIMEOUT = 5.0
NOT_LISTED = "NXDOMAIN"  # the name doesn't exist: the only answer that means "not on the list"
LISTED_PREFIX = "127.0.0."  # a listed IP resolves to 127.0.0.x; 127.255.255.x means "query refused"

Resolve = Callable[[str], Awaitable[Optional[str]]]


_NX_ERRORS = {getattr(socket, n) for n in ("EAI_NONAME", "EAI_NODATA") if hasattr(socket, n)}


async def system_resolve(name: str) -> Optional[str]:
    """First IPv4 address for name, NOT_LISTED if the name doesn't exist, None for any other error
    (timeout, SERVFAIL, no network) – those must not be mistaken for "not listed"."""
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(name, None, family=socket.AF_INET)
    except socket.gaierror as e:
        return NOT_LISTED if e.errno in _NX_ERRORS else None
    except OSError:
        return None
    return infos[0][4][0] if infos else None


def query_name(ip: str, zone: str = ZONE) -> Optional[str]:
    parts = ip.split(".")
    if len(parts) != 4 or not all(p.isdigit() and 0 <= int(p) <= 255 for p in parts):
        return None
    return ".".join(reversed(parts)) + "." + zone


class Blocklist:
    def __init__(self, resolve: Resolve = system_resolve, zone: str = ZONE):
        self.resolve = resolve
        self.zone = zone
        self.usable: Optional[bool] = None  # None until probed
        self.listed = 0
        self._cache: Dict[str, Optional[bool]] = {}
        # lookups still running, one per IP: parallel checks of proxies with the same exit IP share it
        self._inflight: Dict[str, "asyncio.Future[Optional[bool]]"] = {}
        self._slots: Optional[asyncio.Semaphore] = None

    async def probe(self) -> bool:
        """Does the resolver get real answers? 127.0.0.2 must be listed, 127.0.0.1 must not."""
        test = await self._ask(query_name("127.0.0.2", self.zone))
        clean = await self._ask(query_name("127.0.0.1", self.zone))
        self.usable = bool(test and test.startswith(LISTED_PREFIX)) and clean == NOT_LISTED
        return self.usable

    async def _ask(self, name: str) -> Optional[str]:
        try:
            return await asyncio.wait_for(self.resolve(name), LOOKUP_TIMEOUT)
        except asyncio.TimeoutError:
            return None

    async def lookup(self, ip: str) -> Optional[bool]:
        """True = listed, False = not listed, None = unknown (not probed, refused or not an IPv4)."""
        if not self.usable:
            return None
        if ip in self._cache:
            return self._cache[ip]
        if query_name(ip, self.zone) is None:
            return None
        task = self._inflight.get(ip)
        if task is None:
            task = asyncio.ensure_future(self._lookup(ip))
            self._inflight[ip] = task
            task.add_done_callback(lambda t: self._finished(ip, t))
        # shield: a caller that gets cancelled (its check timed out) must not cancel the query the
        # others are waiting for. The query itself always ends – _ask has a timeout.
        return await asyncio.shield(task)

    def _finished(self, ip: str, task: "asyncio.Future[Optional[bool]]") -> None:
        if self._inflight.get(ip) is task:
            del self._inflight[ip]
        if not task.cancelled():
            task.exception()  # retrieved: no "never retrieved" warning when every caller gave up

    async def _lookup(self, ip: str) -> Optional[bool]:
        name = query_name(ip, self.zone)
        if self._slots is None:  # created here: before Python 3.10 a semaphore is bound to the event loop
            self._slots = asyncio.Semaphore(CONCURRENT_LOOKUPS)
        async with self._slots:
            answer = await self._ask(name)
        if answer == NOT_LISTED:
            result: Optional[bool] = False
        elif answer and answer.startswith(LISTED_PREFIX):
            result = True
        else:
            result = None  # an error, a timeout, or 127.255.255.x (the operator refused to answer)
        self._cache[ip] = result
        self.listed += bool(result)
        return result
