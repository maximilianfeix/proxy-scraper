"""The pool of proxies that were found: selection, scoring and who drops out of the rotation.

Selection per connection in three steps:
  1. filters from the request (Selection): country, type – via the user name, e.g. "country-de-type-socks5"
  2. sticky: the same session (or with --sticky the same target site) keeps the same proxy for a while
  3. strategy for everything else: weighted (default), random, round-robin, fastest
"""

from __future__ import annotations

import random
import re
import time
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Set, Tuple

from ..checker import CheckResult

DISABLE_AFTER = 3           # this many failures in a row -> out of the rotation
STRATEGIES = ("weighted", "random", "round-robin", "fastest")
SESSION_SECONDS = 600       # how long a session (session-…) keeps its proxy when --sticky isn't set
_TOKEN_RE = re.compile(r"(country|type|session)[-_]([A-Za-z0-9]+)")


@dataclass(frozen=True)
class Selection:
    """The client's wishes for this connection – they come from the user name of the proxy login."""
    country: str = ""
    ptype: str = ""
    session: str = ""

    @classmethod
    def from_username(cls, username: str) -> "Selection":
        """'country-de-session-abc' -> Selection(country='DE', session='abc'). Unknown parts are ignored."""
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


ANY = Selection()  # no special wishes


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
        # prefer fast and proven ones, but give everyone a chance
        reliability = (self.ok + 1) / (self.ok + self.fail + 2)
        return reliability / (self.result.latency + 300)


class ProxyPool:
    def __init__(self, results: List[CheckResult], rng: Optional[random.Random] = None,
                 strategy: str = "weighted", sticky_seconds: float = 0,
                 clock: Callable[[], float] = time.monotonic):
        if strategy not in STRATEGIES:
            raise ValueError(f"unknown strategy {strategy!r} (possible: {', '.join(STRATEGIES)})")
        self.entries = [PoolEntry(r) for r in sorted(results, key=lambda r: r.latency)]
        self.rng = rng or random.Random()
        self.strategy = strategy
        self.sticky_seconds = sticky_seconds
        self.clock = clock
        self._sticky: Dict[str, Tuple[PoolEntry, float]] = {}  # session/target site -> (proxy, valid until)
        self._next = 0  # for round-robin

    @property
    def usable(self) -> List[PoolEntry]:
        return [e for e in self.entries if not e.disabled]

    @property
    def tls_capable(self) -> List[PoolEntry]:
        return [e for e in self.usable if e.result.https]

    def pick(self, exclude: Set[str], tls: bool = False, selection: Selection = ANY,
             target: str = "") -> Optional[PoolEntry]:
        """Next proxy for a connection to `target` (host:port). None = none fits (any more).

        For TLS only proxies that passed the HTTPS test (verified TLS) – others often break up the
        encryption. If there are none, all of them. Country and type wishes are strict, though:
        whoever asks for "country-de" would rather get an error than a proxy from another country."""
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
            if len(self._sticky) > 10_000:  # don't collect old entries forever
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
            # the fastest free one; if all are busy, the least busy one (then the faster one)
            idle = [e for e in candidates if not e.active]
            if idle:
                return min(idle, key=lambda e: (e.result.latency, -e.weight))
            return min(candidates, key=lambda e: (e.active, e.result.latency))
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
                # if a session holds this proxy, it should get a different one next time
                self._sticky = {k: v for k, v in self._sticky.items() if v[0] is not entry}

    def session_entry(self, session: str) -> Optional[PoolEntry]:
        """The proxy that currently serves a session (username session-NAME) – after failover, the one that worked."""
        held = self._sticky.get(f"session:{session}")
        return held[0] if held else None

    def merge(self, results: List[CheckResult]) -> int:
        """Hits of a refill: new ones join the rotation, known ones that were disabled come back with the fresh
        result, disabled ones that didn't pass again are dropped. Counters of known proxies stay. -> added."""
        fresh = {r.key: r for r in results}
        kept, added = [], 0
        for entry in self.entries:
            r = fresh.pop(entry.result.key, None)
            if r is not None:
                entry.result = r
                if entry.disabled:
                    self.revive(entry)
            elif entry.disabled:
                continue  # dead and not in the fresh list – make room
            kept.append(entry)
        for r in fresh.values():
            kept.append(PoolEntry(r))
            added += 1
        self.entries = sorted(kept, key=lambda e: e.result.latency)
        return added

    def revive(self, entry: PoolEntry) -> None:
        """A disabled proxy passed the recheck – back into the rotation."""
        entry.disabled = False
        entry.fail_streak = 0
