"""Der Pool gefundener Proxys: Auswahl, Bewertung und wer aus der Rotation fliegt.

Auswahl pro Verbindung in drei Schritten:
  1. Filter aus der Anfrage (Selection): Land, Typ – über den Benutzernamen, z. B. "country-de-type-socks5"
  2. Sticky: dieselbe Session (oder mit --sticky dieselbe Zielseite) bekommt eine Weile denselben Proxy
  3. Strategie für alles andere: weighted (Standard), random, round-robin, fastest
"""

from __future__ import annotations

import random
import re
import time
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Set, Tuple

from ..checker import CheckResult

DISABLE_AFTER = 3           # so viele Fehlschläge hintereinander -> aus der Rotation
STRATEGIES = ("weighted", "random", "round-robin", "fastest")
SESSION_SECONDS = 600       # so lange hält eine Session (session-…) ihren Proxy, wenn --sticky nicht gesetzt ist
_TOKEN_RE = re.compile(r"(country|type|session)[-_]([A-Za-z0-9]+)")


@dataclass(frozen=True)
class Selection:
    """Wünsche des Clients für diese Verbindung – kommen aus dem Benutzernamen der Proxy-Anmeldung."""
    country: str = ""
    ptype: str = ""
    session: str = ""

    @classmethod
    def from_username(cls, username: str) -> "Selection":
        """'country-de-session-abc' -> Selection(country='DE', session='abc'). Unbekanntes wird ignoriert."""
        found = dict(_TOKEN_RE.findall(username or ""))
        ptype = found.get("type", "").lower()
        return cls(country=found.get("country", "").upper()[:2],
                   ptype=ptype if ptype in ("http", "socks4", "socks5") else "",
                   session=found.get("session", "")[:64])

    def __bool__(self) -> bool:
        return bool(self.country or self.ptype or self.session)

    def describe(self) -> str:
        parts = [self.country, self.ptype, f"session {self.session}" if self.session else ""]
        return " · ".join(p for p in parts if p)


ANY = Selection()  # keine besonderen Wünsche


@dataclass
class PoolEntry:
    result: CheckResult
    ok: int = 0
    fail: int = 0
    fail_streak: int = 0
    active: int = 0
    disabled: bool = False

    @property
    def weight(self) -> float:
        # Schnell und bewährt bevorzugen, aber allen eine Chance geben
        reliability = (self.ok + 1) / (self.ok + self.fail + 2)
        return reliability / (self.result.latency + 300)


class ProxyPool:
    def __init__(self, results: List[CheckResult], rng: Optional[random.Random] = None,
                 strategy: str = "weighted", sticky_seconds: float = 0,
                 clock: Callable[[], float] = time.monotonic):
        if strategy not in STRATEGIES:
            raise ValueError(f"unbekannte Strategie {strategy!r} (möglich: {', '.join(STRATEGIES)})")
        self.entries = [PoolEntry(r) for r in sorted(results, key=lambda r: r.latency)]
        self.rng = rng or random.Random()
        self.strategy = strategy
        self.sticky_seconds = sticky_seconds
        self.clock = clock
        self._sticky: Dict[str, Tuple[PoolEntry, float]] = {}  # Session/Zielseite -> (Proxy, gültig bis)
        self._next = 0  # für round-robin

    @property
    def usable(self) -> List[PoolEntry]:
        return [e for e in self.entries if not e.disabled]

    @property
    def tls_capable(self) -> List[PoolEntry]:
        return [e for e in self.usable if e.result.https]

    def pick(self, exclude: Set[str], tls: bool = False, selection: Selection = ANY,
             target: str = "") -> Optional[PoolEntry]:
        """Nächster Proxy für eine Verbindung zu `target` (host:port). None = keiner passt (mehr).

        Für TLS nur Proxys, die den HTTPS-Test (verifiziertes TLS) bestanden haben – andere brechen die
        Verschlüsselung oft auf. Gibt es keine, dann alle. Länder- und Typwünsche gelten dagegen streng:
        wer "country-de" verlangt, bekommt lieber einen Fehler als einen Proxy aus einem anderen Land."""
        candidates = [e for e in self.usable if e.result.key not in exclude and self._matches(e, selection)]
        if tls and any(e.result.https for e in self.usable if self._matches(e, selection)):
            candidates = [e for e in candidates if e.result.https]
        if not candidates:
            return None
        sticky_key = self._sticky_key(selection, target)
        if sticky_key:
            held = self._sticky.get(sticky_key)
            if held and held[1] > self.clock() and held[0] in candidates:
                return held[0]
        entry = self._choose(candidates)
        if sticky_key:
            self._sticky[sticky_key] = (entry, self.clock() + (self.sticky_seconds or SESSION_SECONDS))
            if len(self._sticky) > 10_000:  # alte Einträge nicht endlos sammeln
                now = self.clock()
                self._sticky = {k: v for k, v in self._sticky.items() if v[1] > now}
        return entry

    def _sticky_key(self, selection: Selection, target: str) -> str:
        if selection.session:
            return f"session:{selection.session}"
        if self.sticky_seconds and target:
            return f"target:{target}"
        return ""

    @staticmethod
    def _matches(entry: PoolEntry, selection: Selection) -> bool:
        r = entry.result
        return (not selection.country or r.country == selection.country) and \
            (not selection.ptype or r.ptype == selection.ptype)

    def _choose(self, candidates: List[PoolEntry]) -> PoolEntry:
        if self.strategy == "random":
            return self.rng.choice(candidates)
        if self.strategy == "fastest":
            # schnellster zuerst, bei Gleichstand der zuverlässigere; wenig beschäftigte bevorzugen
            return min(candidates, key=lambda e: (e.result.latency + 200 * e.active, -e.weight))
        if self.strategy == "round-robin":
            ordered = sorted(candidates, key=lambda e: e.result.key)
            entry = ordered[self._next % len(ordered)]
            self._next += 1
            return entry
        return self.rng.choices(candidates, weights=[e.weight for e in candidates])[0]

    def report(self, entry: PoolEntry, ok: bool) -> None:
        if ok:
            entry.ok += 1
            entry.fail_streak = 0
        else:
            entry.fail += 1
            entry.fail_streak += 1
            if entry.fail_streak >= DISABLE_AFTER:
                entry.disabled = True
                # hält eine Session diesen Proxy, soll sie beim nächsten Mal einen anderen bekommen
                self._sticky = {k: v for k, v in self._sticky.items() if v[0] is not entry}

    def revive(self, entry: PoolEntry) -> None:
        """Ein ausgemusterter Proxy hat die Nachprüfung bestanden – zurück in die Rotation."""
        entry.disabled = False
        entry.fail_streak = 0
