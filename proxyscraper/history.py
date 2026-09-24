"""Verlauf funktionierender Proxys über Läufe hinweg.

Ein Proxy, der gestern lief, läuft heute mit viel höherer Wahrscheinlichkeit als ein
beliebiger Listeneintrag – deshalb werden bekannte Proxys zuerst geprüft.
"""

from __future__ import annotations

import json
import time
import warnings
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional

from .paths import DATA_DIR, atomic_write

HISTORY_FILE = DATA_DIR / "proxy_history.json"
DAY = 86400.0
FORGET_AFTER = 14 * DAY     # so lange nicht mehr funktioniert -> vergessen
MAX_FAIL_STREAK = 4         # so oft hintereinander tot -> vergessen


@dataclass
class ProxyRecord:
    first_ok: float = 0.0
    last_ok: float = 0.0
    ok: int = 0
    fail: int = 0
    fail_streak: int = 0
    latency: int = 0
    exit_ip: str = ""
    country: str = ""
    anonymity: str = ""
    https: Optional[bool] = None

    @property
    def reliability(self) -> float:
        """Anteil erfolgreicher Prüfungen, geglättet (1 von 1 ist nicht 100 %)."""
        return (self.ok + 1) / (self.ok + self.fail + 2)


class ProxyHistory:
    def __init__(self, path: Path = HISTORY_FILE):
        self.path = path
        self.records: Dict[str, ProxyRecord] = {}
        if path.exists():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                self.records = {k: ProxyRecord(**v) for k, v in raw.items()}
            except (OSError, ValueError, TypeError) as e:
                warnings.warn(f"{path.name} unlesbar ({e}), starte ohne Proxy-Verlauf", stacklevel=2)

    @staticmethod
    def exists(path: Path = HISTORY_FILE) -> bool:
        """Gibt es einen nicht leeren Verlauf? Ohne ihn komplett zu laden."""
        try:
            return path.stat().st_size > 2  # "{}" = leer
        except OSError:
            return False

    def __len__(self) -> int:
        return len(self.records)

    def __contains__(self, key: str) -> bool:
        return key in self.records

    def get(self, key: str) -> Optional[ProxyRecord]:
        return self.records.get(key)

    def ranked_keys(self) -> List[str]:
        """Bekannte Proxys, zuverlässigste und zuletzt erfolgreiche zuerst."""
        return sorted(self.records, key=lambda k: (-self.records[k].reliability, -self.records[k].last_ok))

    def record_ok(self, key: str, latency: int, exit_ip: str, now: Optional[float] = None, **details) -> None:
        now = time.time() if now is None else now
        rec = self.records.setdefault(key, ProxyRecord(first_ok=now))
        rec.last_ok = now
        rec.ok += 1
        rec.fail_streak = 0
        rec.latency = latency
        rec.exit_ip = exit_ip
        for name, value in details.items():
            if value not in (None, ""):
                setattr(rec, name, value)

    def record_fail(self, key: str) -> None:
        """Nur für bereits bekannte Proxys – sonst würde der Verlauf mit Millionen toter Einträge volllaufen."""
        rec = self.records.get(key)
        if rec:
            rec.fail += 1
            rec.fail_streak += 1

    def prune(self, now: Optional[float] = None) -> int:
        now = time.time() if now is None else now
        dead = [
            k for k, r in self.records.items()
            if r.fail_streak >= MAX_FAIL_STREAK or now - r.last_ok > FORGET_AFTER
        ]
        for k in dead:
            del self.records[k]
        return len(dead)

    def save(self) -> None:
        payload = {k: asdict(r) for k, r in self.records.items()}
        atomic_write(self.path, json.dumps(payload, separators=(",", ":")))
