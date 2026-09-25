"""The live proxy list as the bot sees it: fetch it, filter it, turn it into text.

Nothing in here talks to Discord, so all of it can be tested without a bot token.
The data is the same the website uses: stats.json, proxies.json and history.json from GitHub Pages.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Sequence

TYPES = ("http", "socks4", "socks5")


@dataclass(frozen=True)
class Proxy:
    ptype: str
    address: str
    latency: int
    country: str = ""
    https: bool = False
    anonymity: str = ""
    hosting: bool = False
    org: str = ""
    streak: int = 0
    blocklisted: Optional[bool] = None  # exit IP on SpamCop? None = not looked up

    @property
    def url(self) -> str:
        return f"{self.ptype}://{self.address}"

    @classmethod
    def from_row(cls, row: dict) -> Optional["Proxy"]:
        """One entry of proxies.json -> Proxy, None if the entry is unusable."""
        ptype, address = row.get("ptype"), row.get("proxy")
        if ptype not in TYPES or not isinstance(address, str) or not address:
            return None
        try:
            latency = int(row.get("latency") or 0)
        except (TypeError, ValueError):
            return None
        blocklisted = row.get("blocklisted")
        return cls(ptype, address, latency, str(row.get("country") or ""), bool(row.get("https")),
                   str(row.get("anonymity") or ""), bool(row.get("hosting")), str(row.get("org") or ""),
                   int(row.get("streak") or 0), blocklisted if isinstance(blocklisted, bool) else None)


@dataclass
class Snapshot:
    """One run of the live list."""

    updated: datetime
    stats: dict
    proxies: List[Proxy]
    history: List[dict] = field(default_factory=list)

    @property
    def run_id(self) -> str:
        return self.updated.isoformat()

    def previous_total(self) -> Optional[int]:
        """Total of the run before this one, for the trend in the summary."""
        earlier = [h for h in self.history if h.get("updated") != self.stats.get("updated")]
        return earlier[-1].get("total") if earlier else None


def parse_snapshot(stats: dict, rows: Sequence[dict], history: Optional[Sequence[dict]] = None) -> Snapshot:
    updated = datetime.fromisoformat(stats["updated"])
    proxies = [p for p in (Proxy.from_row(r) for r in rows if isinstance(r, dict)) if p]
    proxies.sort(key=lambda p: p.latency)
    return Snapshot(updated, stats, proxies, [h for h in history or [] if isinstance(h, dict)])


def select(proxies: Iterable[Proxy], ptype: str = "", country: str = "", https: bool = False, elite: bool = False,
           no_datacenter: bool = False, stable: bool = False, max_latency: int = 0,
           not_blocklisted: bool = False) -> List[Proxy]:
    """Filter like the website does, fastest first."""
    country = country.strip().upper()
    out = [p for p in proxies
           if (not ptype or p.ptype == ptype)
           and (not country or p.country == country)
           and (not https or p.https)
           and (not elite or p.anonymity == "elite")
           and (not no_datacenter or not p.hosting)
           and (not not_blocklisted or not p.blocklisted)
           and (not stable or p.streak >= 4)
           and (not max_latency or p.latency <= max_latency)]
    return sorted(out, key=lambda p: p.latency)


def pick_one(proxies: Sequence[Proxy], rng: Optional[random.Random] = None) -> Optional[Proxy]:
    """A random one of the 20 fastest – good enough and not always the same one for everybody."""
    if not proxies:
        return None
    return (rng or random).choice(list(proxies)[:20])


def as_lines(proxies: Iterable[Proxy]) -> str:
    """type://ip:port, one per line – the same format as all.txt."""
    return "".join(f"{p.url}\n" for p in proxies)


def table(proxies: Sequence[Proxy], limit: int) -> str:
    """Aligned plain-text table for a Discord code block."""
    shown = list(proxies)[:limit]
    if not shown:
        return "no matching proxy"
    width = max(len(p.url) for p in shown)
    lines = []
    for p in shown:
        flags = " ".join(x for x in (p.country or "--", "https" if p.https else "", p.anonymity) if x)
        lines.append(f"{p.url.ljust(width)}  {str(p.latency).rjust(5)} ms  {flags}")
    return "\n".join(lines)


def top_countries(stats: dict, n: int = 5) -> List[str]:
    countries: Dict[str, int] = stats.get("countries") or {}
    return [f"{cc} {count:,}" for cc, count in list(countries.items())[:n]]


def pct(part: int, whole: int) -> str:
    return f"{100 * part / whole:.0f}%" if whole else "–"
