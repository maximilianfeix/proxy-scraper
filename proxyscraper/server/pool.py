"""Der Pool gefundener Proxys: Auswahl, Bewertung und wer aus der Rotation fliegt."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import List, Optional, Set

from ..checker import CheckResult

DISABLE_AFTER = 3           # so viele Fehlschläge hintereinander -> aus der Rotation


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
    def __init__(self, results: List[CheckResult], rng: Optional[random.Random] = None):
        self.entries = [PoolEntry(r) for r in sorted(results, key=lambda r: r.latency)]
        self.rng = rng or random.Random()

    @property
    def usable(self) -> List[PoolEntry]:
        return [e for e in self.entries if not e.disabled]

    @property
    def tls_capable(self) -> List[PoolEntry]:
        return [e for e in self.usable if e.result.https]

    def pick(self, exclude: Set[str], tls: bool = False) -> Optional[PoolEntry]:
        """Gewichtete Zufallswahl. Für TLS nur Proxys, die den HTTPS-Test (verifiziertes TLS) bestanden
        haben – andere brechen die Verschlüsselung oft auf. Gibt es keine, dann alle."""
        candidates = [e for e in self.usable if e.result.key not in exclude]
        if tls and any(e.result.https for e in self.usable):
            candidates = [e for e in candidates if e.result.https]
        if not candidates:
            return None
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
