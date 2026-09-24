"""Prüfziele: Dienste, die nur die IP des Absenders als Text zurückgeben.

Jeder Proxy muss über ein Prüfziel seine Exit-IP abrufen. Fällt das Ziel aus oder drosselt es,
sieht jeder Proxy tot aus – und die Quellen-Statistik würde daraus falsch lernen. Deshalb:

- vor dem Lauf alle Ziele direkt testen und das beste erreichbare nehmen
- während des Laufs regelmäßig nachsehen (JudgeWatch) und bei Ausfall wechseln

Ziele hinter Cloudflare sind tabu: Viele "Proxys" in den Listen sind Cloudflare-Adressen, die eine
Anfrage an eine Cloudflare-Seite einfach selbst beantworten und so als funktionierend durchgingen.
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
        """host[:port] für Host-Header und URLs."""
        return self.host if self.port == 80 else f"{self.host}:{self.port}"


# Reihenfolge = Eignung. Gemessen mit denselben 300 zuletzt funktionierenden Proxys (September 2026):
# amazonaws 255, ifconfig.me 230, ipinfo.io 223, wtfismyip 213, ident.me 199 Treffer.
# Die direkte Latenz sagt darüber wenig – manche Dienste lehnen Proxys einfach öfter ab.
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
    seen_ip: str = ""  # was das Ziel als unsere IP gesehen hat (Reserve, falls get_own_ips scheitert)


async def probe_judge(judge: Judge, timeout: float = 5.0) -> Optional[JudgeProbe]:
    """Ziel direkt (ohne Proxy) abfragen. None = nicht erreichbar, falsche Antwort oder Cloudflare."""
    loop = asyncio.get_running_loop()
    try:
        infos = await asyncio.wait_for(loop.getaddrinfo(judge.host, judge.port, family=socket.AF_INET), timeout)
    except Exception:
        return None
    addresses = list(dict.fromkeys(info[4][0] for info in infos))
    if any(behind_cloudflare(ip) for ip in addresses):
        return None  # auch nur teilweise hinter Cloudflare reicht, um es auszuschließen
    for ip in addresses:  # erste funktionierende Adresse – genau die nutzt später auch der Checker
        start = time.perf_counter()
        seen = await _ask(ip, judge, timeout)
        if seen:
            return JudgeProbe(judge, ip, round((time.perf_counter() - start) * 1000), seen)
    return None


async def _ask(ip: str, judge: Judge, timeout: float) -> str:
    """Das Ziel über genau diese Adresse fragen -> die IP, die es sieht ('' bei Fehler)."""
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
        # Direkt kann hier auch IPv6 zurückkommen (z. B. iCloud Private Relay) – über Proxys sprechen wir
        # das Ziel per IPv4-Adresse an und bekommen dann die IPv4-Exit-IP
        ipaddress.ip_address(seen)
    except Exception:  # Timeout, Verbindungsfehler, keine IP im Body – alles heißt "gerade unbrauchbar"
        return ""
    return seen if status == 200 else ""


async def rank_judges(judges=JUDGES, timeout: float = 5.0, probe=probe_judge) -> List[JudgeProbe]:
    """Alle Ziele parallel testen; die erreichbaren in Reihenfolge ihrer Eignung (siehe JUDGES)."""
    results = await asyncio.gather(*(probe(j, timeout) for j in judges))
    return [r for r in results if r]


class JudgeWatch:
    """Behält das Prüfziel während des Laufs im Blick und wechselt, wenn es ausfällt.

    on_ok wird nach jeder erfolgreichen Kontrolle aufgerufen, on_switch(alt, neu) beim Wechsel –
    der Aufrufer kann so die Prüfungen seit der letzten guten Kontrolle als verdächtig behandeln.
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
                self.reserve.append(old)  # vielleicht ist es später wieder da
                self.current, self.failures = fresh, 0
                self.switch(fresh)
                self.switches.append(f"{old.judge.host} → {fresh.judge.host}")
                self.on_switch(old, fresh)
                return
