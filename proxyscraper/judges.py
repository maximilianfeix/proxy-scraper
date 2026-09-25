"""Check targets ("judges"): services that return nothing but the sender's IP as text.

Every proxy has to fetch its exit IP from a check target. If the target goes down or throttles,
every proxy looks dead – and the source statistics would learn the wrong thing from it. So:

- test every target directly before the run and take the best reachable one
- check regularly during the run (JudgeWatch) and switch if it goes down

Targets behind Cloudflare are off limits: many "proxies" in the lists are Cloudflare addresses that
simply answer a request to a Cloudflare site themselves and would pass as working that way.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
import time
from dataclasses import dataclass
from typing import Awaitable, Callable, List, Optional

from .netio import read_response


@dataclass(frozen=True)
class Judge:
    host: str
    path: str = "/"
    port: int = 80

    @property
    def authority(self) -> str:
        """host[:port] for Host headers and URLs."""
        return self.host if self.port == 80 else f"{self.host}:{self.port}"


# order = suitability. Measured with the same 300 most recently working proxies (September 2026):
# amazonaws 255, ifconfig.me 230, ipinfo.io 223, wtfismyip 213, ident.me 199 hits.
# The direct latency says little about it – some services simply reject proxies more often.
JUDGES = (
    Judge("checkip.amazonaws.com"),   # AWS
    Judge("ifconfig.me", "/ip"),      # Google Cloud
    Judge("ipinfo.io", "/ip"),        # Google Cloud
    Judge("wtfismyip.com", "/text"),
    Judge("ident.me"),                # Hetzner
)
DEFAULT_JUDGE = JUDGES[0]

# https://www.cloudflare.com/ips-v4/
CLOUDFLARE_V4 = tuple(ipaddress.IPv4Network(n) for n in (
    "173.245.48.0/20", "103.21.244.0/22", "103.22.200.0/22", "103.31.4.0/22", "141.101.64.0/18",
    "108.162.192.0/18", "190.93.240.0/20", "188.114.96.0/20", "197.234.240.0/22", "198.41.128.0/17",
    "162.158.0.0/15", "104.16.0.0/13", "104.24.0.0/14", "172.64.0.0/13", "131.0.72.0/22",
))


def behind_cloudflare(ip: str) -> bool:
    addr = ipaddress.IPv4Address(ip)
    return any(addr in net for net in CLOUDFLARE_V4)


@dataclass(frozen=True)
class JudgeProbe:
    judge: Judge
    ip: str
    latency: int  # ms
    seen_ip: str = ""  # what the target saw as our IP (fallback in case get_own_ips fails)


async def probe_judge(judge: Judge, timeout: float = 5.0) -> Optional[JudgeProbe]:
    """Query the target directly (without a proxy). None = unreachable, wrong answer or Cloudflare."""
    loop = asyncio.get_running_loop()
    try:
        infos = await asyncio.wait_for(loop.getaddrinfo(judge.host, judge.port, family=socket.AF_INET), timeout)
    except Exception:
        return None
    addresses = list(dict.fromkeys(info[4][0] for info in infos))
    if any(behind_cloudflare(ip) for ip in addresses):
        return None  # being behind Cloudflare even partially is enough to exclude it
    for ip in addresses:  # first working address – exactly that one is used by the checker later
        start = time.perf_counter()
        seen = await _ask(ip, judge, timeout)
        if seen:
            return JudgeProbe(judge, ip, round((time.perf_counter() - start) * 1000), seen)
    return None


async def _ask(ip: str, judge: Judge, timeout: float) -> str:
    """Ask the target via exactly this address -> the IP it sees ('' on error)."""
    request = (f"GET {judge.path} HTTP/1.1\r\nHost: {judge.authority}\r\nUser-Agent: Mozilla/5.0\r\n"
               f"Connection: close\r\n\r\n").encode()
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(ip, judge.port), timeout)
        try:
            writer.write(request)
            await writer.drain()
            status, _, body = await asyncio.wait_for(read_response(reader), timeout)
        finally:
            writer.close()
        seen = body.strip().decode("ascii", "ignore")
        # directly this may also return IPv6 (e.g. iCloud Private Relay) – through proxies we address
        # the target by its IPv4 address and then get the IPv4 exit IP
        ipaddress.ip_address(seen)
    except Exception:  # timeout, connection error, no IP in the body – all mean "unusable right now"
        return ""
    return seen if status == 200 else ""


async def rank_judges(judges=JUDGES, timeout: float = 5.0, probe=probe_judge) -> List[JudgeProbe]:
    """Test every target in parallel; the reachable ones in order of suitability (see JUDGES)."""
    results = await asyncio.gather(*(probe(j, timeout) for j in judges))
    return [r for r in results if r]


class JudgeWatch:
    """Keeps an eye on the check target during the run and switches if it goes down.

    on_ok is called after every successful probe, on_switch(old, new) on a switch –
    that way the caller can treat the checks since the last good probe as suspicious.
    """

    def __init__(self, ranked: List[JudgeProbe], switch: Callable[[JudgeProbe], None],
                 interval: float = 15.0, failures_before_switch: int = 2,
                 probe: Callable[..., Awaitable[Optional[JudgeProbe]]] = probe_judge):
        self.current = ranked[0]
        self.reserve = list(ranked[1:])
        self.switch = switch
        self.interval = interval
        self.failures_before_switch = failures_before_switch
        self.probe = probe
        self.failures = 0
        self.switches: List[str] = []
        self.on_ok: Callable[[], None] = lambda: None
        self.on_switch: Callable[[JudgeProbe, JudgeProbe], None] = lambda old, new: None

    async def run(self) -> None:
        while True:
            await asyncio.sleep(self.interval)
            await self.check_once()

    async def check_once(self) -> None:
        if await self.probe(self.current.judge):
            self.failures = 0
            self.on_ok()
            return
        self.failures += 1
        if self.failures < self.failures_before_switch:
            return
        for candidate in list(self.reserve):
            fresh = await self.probe(candidate.judge)
            if fresh:
                old = self.current
                self.reserve.remove(candidate)
                self.reserve.append(old)  # maybe it comes back later
                self.current, self.failures = fresh, 0
                self.switch(fresh)
                self.switches.append(f"{old.judge.host} → {fresh.judge.host}")
                self.on_switch(old, fresh)
                return
