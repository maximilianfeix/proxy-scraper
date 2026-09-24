"""Länder der Exit-IPs.

Zuerst offline aus der DB-IP-Datenbank (geodb.py) – sofort und ohne Limit. Nur was dort fehlt
(oder wenn die Datenbank nicht geladen werden konnte), geht an die Batch-API von ip-api.com
(100 IPs pro Anfrage, 15 Anfragen/Minute, läuft im Hintergrund). API-Ergebnisse werden
zwischengespeichert, damit bekannte IPs nie erneut abgefragt werden.
"""

from __future__ import annotations

import asyncio
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
MIN_INTERVAL = 4.2          # 60 s / 15 Anfragen, plus Puffer
CACHE_TTL = 30 * 86400.0


def flag(country: str) -> str:
    """'DE' -> 🇩🇪 (aus Regional-Indicator-Zeichen zusammengesetzt)."""
    if len(country) != 2 or not country.isalpha():
        return "  "
    return "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in country.upper())


class GeoResolver:
    def __init__(self, enabled: bool = True, on_resolved: Optional[Callable[[str, str], None]] = None,
                 offline: Optional[CountryDB] = None):
        self.enabled = enabled
        self.offline = offline
        self.offline_hits = 0
        self.on_resolved = on_resolved
        self.cache: Dict[str, List] = {}  # ip -> [land, zeitpunkt]
        self.pending: List[str] = []
        self._queued = set()
        self._stop = asyncio.Event()
        self.failed = False
        if GEO_CACHE_FILE.exists():
            try:
                self.cache = json.loads(GEO_CACHE_FILE.read_text(encoding="utf-8"))
            except (OSError, ValueError) as e:
                warnings.warn(f"{GEO_CACHE_FILE.name} unlesbar ({e})", stacklevel=2)

    def lookup(self, ip: str) -> str:
        hit = self.cache.get(ip)
        return hit[0] if hit and time.time() - hit[1] < CACHE_TTL else ""

    def use_offline(self, db: CountryDB) -> None:
        """Neue Datenbank mitten im Lauf übernehmen – auch für IPs, die schon auf ip-api warten,
        damit dieselbe Exit-IP nicht einmal so und einmal anders eingeordnet wird."""
        self.offline = db
        waiting, self.pending = self.pending, []
        for ip in waiting:
            country = db.lookup(ip)
            if not country:
                self.pending.append(ip)
                continue
            self.offline_hits += 1
            if self.on_resolved:
                self.on_resolved(ip, country)

    def request(self, ip: str) -> str:
        """Land sofort (offline oder aus dem Cache), sonst für die nächste Batch-Anfrage vormerken."""
        if self.enabled and self.offline:
            country = self.offline.lookup(ip)
            if country:
                self.offline_hits += 1
                return country
        country = self.lookup(ip)
        if not country and self.enabled and ip not in self._queued:
            self._queued.add(ip)
            self.pending.append(ip)
        return country

    async def run(self) -> None:
        """Hintergrundschleife – endet nach stop(), sobald nichts mehr offen ist."""
        if not self.enabled:
            return
        while not (self._stop.is_set() and not self.pending):
            if not self.pending:
                try:
                    await asyncio.wait_for(self._stop.wait(), 0.5)
                except asyncio.TimeoutError:
                    pass
                continue
            batch, self.pending = self.pending[:BATCH_SIZE], self.pending[BATCH_SIZE:]
            started = time.monotonic()
            wait = await self._resolve(batch)
            if self.failed:
                return
            await asyncio.sleep(max(wait, MIN_INTERVAL - (time.monotonic() - started)))

    async def _resolve(self, batch: List[str]) -> float:
        """Eine Batch-Anfrage; gibt die nötige Wartezeit bis zur nächsten zurück."""
        try:
            status, headers, body = await http_request(
                BATCH_URL, timeout=10, method="POST", body=json.dumps(batch).encode(),
                headers={"Content-Type": "application/json"},
            )
        except Exception:  # API nicht erreichbar -> Länder bleiben leer, der Rest läuft weiter
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
                if self.offline and self.offline.lookup(ip):
                    continue  # inzwischen kennt die Datenbank sie – use_offline hat sie schon gemeldet
                if self.on_resolved:
                    self.on_resolved(ip, country)
        # Wenn ip-api das Limit fast erreicht meldet, bis zum Reset warten
        if headers.get(b"x-rl", b"1") == b"0":
            return float(headers.get(b"x-ttl", b"60") or 60)
        return 0.0

    def stop(self) -> None:
        self._stop.set()

    def save(self) -> None:
        if self.cache:
            atomic_write(GEO_CACHE_FILE, json.dumps(self.cache, separators=(",", ":")))
