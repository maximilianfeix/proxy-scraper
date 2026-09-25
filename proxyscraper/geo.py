"""Countries of the exit IPs.

First offline from the DB-IP database (geodb.py) – instantly and without a limit. Only what's missing
there (or when the database couldn't be loaded) goes to the batch API of ip-api.com
(100 IPs per request, 15 requests/minute, runs in the background). API results are cached,
so known IPs are never queried again.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
import warnings
from typing import Callable, Dict, List, Optional

from .geodb import CountryDB
from .netio import http_request
from .paths import DATA_DIR, atomic_write

GEO_CACHE_FILE = DATA_DIR / "geo_cache.json"
BATCH_URL = "http://ip-api.com/batch?fields=status,countryCode,query"
BATCH_SIZE = 100
MIN_INTERVAL = 4.2          # 60 s / 15 requests, plus a buffer
CACHE_TTL = 30 * 86400.0


def flag(country: str) -> str:
    """'DE' -> 🇩🇪 (built from regional indicator characters)."""
    if len(country) != 2 or not country.isalpha():
        return "  "
    return "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in country.upper())


class GeoResolver:
    def __init__(self, enabled: bool = True, on_resolved: Optional[Callable[[str, str], None]] = None,
                 offline: Optional[CountryDB] = None):
        self.enabled = enabled
        self.offline = offline
        self.offline_hits = 0
        # per run every exit IP gets exactly one country – no matter whether it comes from the database, the cache
        # or ip-api, and whether the database only arrives half-way through
        self.assigned: Dict[str, str] = {}
        self.on_resolved = on_resolved
        self.cache: Dict[str, List] = {}  # ip -> [country, timestamp]
        self.pending: List[str] = []
        self._queued = set()
        self._stop = asyncio.Event()
        self.failed = False
        if GEO_CACHE_FILE.exists():
            try:
                self.cache = json.loads(GEO_CACHE_FILE.read_text(encoding="utf-8"))
            except (OSError, ValueError) as e:
                warnings.warn(f"{GEO_CACHE_FILE.name} unreadable ({e})", stacklevel=2)

    def lookup(self, ip: str) -> str:
        hit = self.cache.get(ip)
        return hit[0] if hit and time.time() - hit[1] < CACHE_TTL else ""

    def use_offline(self, db: CountryDB) -> None:
        """Take over a new database mid-run – also for IPs already waiting for ip-api,
        so the same exit IP isn't classified one way once and another way the next time."""
        self.offline = db
        waiting, self.pending = self.pending, []
        for ip in waiting:
            country = db.lookup(ip)
            if not country:
                self.pending.append(ip)
                continue
            self.offline_hits += 1
            self._assign(ip, country)

    def _assign(self, ip: str, country: str) -> None:
        if ip in self.assigned:
            return
        self.assigned[ip] = country
        if self.on_resolved:
            self.on_resolved(ip, country)

    def request(self, ip: str) -> str:
        """Country right away (offline or from the cache), otherwise queue it for the next batch request."""
        if ip in self.assigned:
            return self.assigned[ip]
        country = ""
        if self.enabled and self.offline:
            country = self.offline.lookup(ip)
            if country:
                self.offline_hits += 1
        country = country or self.lookup(ip)
        if country:
            self.assigned[ip] = country
        elif self.enabled and ip not in self._queued:
            self._queued.add(ip)
            self.pending.append(ip)
        return country

    async def run(self) -> None:
        """Background loop – ends after stop() as soon as nothing is pending."""
        if not self.enabled:
            return
        while not (self._stop.is_set() and not self.pending):
            if not self.pending:
                with contextlib.suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(self._stop.wait(), 0.5)
                continue
            batch, self.pending = self.pending[:BATCH_SIZE], self.pending[BATCH_SIZE:]
            started = time.monotonic()
            wait = await self._resolve(batch)
            if self.failed:
                return
            await asyncio.sleep(max(wait, MIN_INTERVAL - (time.monotonic() - started)))

    async def _resolve(self, batch: List[str]) -> float:
        """One batch request; returns the wait time needed before the next one."""
        try:
            status, headers, body = await http_request(
                BATCH_URL, timeout=10, method="POST", body=json.dumps(batch).encode(),
                headers={"Content-Type": "application/json"},
            )
        except Exception:  # API unreachable -> countries stay empty, the rest keeps running
            self.failed = True
            return 0.0
        if status == 429:
            self.pending = batch + self.pending
            return float(headers.get(b"x-ttl", b"60") or 60)
        if status != 200:
            self.failed = True
            return 0.0
        now = time.time()
        try:
            rows = json.loads(body)
        except ValueError:
            return 0.0
        for row in rows:
            if row.get("status") == "success":
                ip, country = row["query"], row["countryCode"]
                self.cache[ip] = [country, now]
                self._assign(ip, country)  # already classified otherwise (e.g. by the database)? keep it
        # if ip-api reports the limit is almost reached, wait for the reset
        if headers.get(b"x-rl", b"1") == b"0":
            return float(headers.get(b"x-ttl", b"60") or 60)
        return 0.0

    def stop(self) -> None:
        self._stop.set()

    def save(self) -> None:
        if self.cache:
            atomic_write(GEO_CACHE_FILE, json.dumps(self.cache, separators=(",", ":")))
