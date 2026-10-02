"""Which proxy is "fastest": how quickly a page comes through, not just the first answer (#186).

A quick answer to one tiny request says little about loading a page – in a test on the live list, the 25 HTTPS
proxies quickest to answer loaded 4 of 50 real pages, the first 25 ranked by answer plus the download speed of the
hourly speed step 26 of 50. Everything that orders proxies of the live list uses this: the published lists, the
pages, --pick, live_proxies, the rotating pool.

On the live list, speed alone isn't enough: most free proxies don't last. Rows that say how many runs in a row they've
been listed (`streak`) are ranked by the page time divided by the chance they still work an hour later (SURVIVAL), so a
fast proxy that showed up once doesn't push out one that has been there all week.
"""

from __future__ import annotations

import statistics
from typing import Iterable, List, Optional

PAGE_KB = 100               # roughly one page – the download the speed step measures
UNMEASURED_KBPS = 20        # tried in the speed step, no download got through: counted as slow (it passed the checks)
# (runs in a row on the list, share still on it one run later) – measured over a week of hourly runs (seen.json,
# 2026-09-29): 25 % of new proxies, 99 % of those listed for a day
SURVIVAL = ((24, 0.99), (12, 0.93), (6, 0.82), (3, 0.61), (2, 0.46), (1, 0.25))


def page_ms(latency: float, speed_kbps: Optional[int], https: Optional[bool], typical_kbps: Optional[float]) -> float:
    """Roughly how long a page takes through a proxy: the first answer plus the download.

    typical_kbps is the median measured speed of the set, None when it has no speeds at all (an own scan) – then
    latency decides alone. The speed step only tries HTTPS-capable proxies: one of those without a speed didn't
    get the download through, the others were never tried and count as typical."""
    if not typical_kbps:
        return latency
    kbps = speed_kbps or (UNMEASURED_KBPS if https else typical_kbps)
    return latency + PAGE_KB * 1000 / kbps


def survival(streak: Optional[int]) -> float:
    """The chance a proxy from the live list still works one run later. 1.0 without a streak: an own scan, the
    proxy was just checked."""
    if type(streak) is not int or streak < 1:
        return 1.0
    return next(share for runs, share in SURVIVAL if streak >= runs)


def expected_ms(latency: float, speed_kbps: Optional[int], https: Optional[bool], typical_kbps: Optional[float],
                streak: Optional[int] = None) -> float:
    """page_ms, weighted by how likely the proxy is still up: dividing by the chance is what it costs on average,
    counting the tries on proxies that have gone in the meantime."""
    return page_ms(latency, speed_kbps, https, typical_kbps) / survival(streak)


def typical_speed(speeds: Iterable[Optional[int]]) -> Optional[float]:
    measured = [s for s in speeds if s]
    return statistics.median(measured) if measured else None


def best_first(rows: Iterable[dict]) -> List[dict]:
    """Rows of a run (dicts as in proxies.json), the fastest to load a page first – counting on the live list how
    likely each one is still up."""
    rows = list(rows)
    typical = typical_speed(_speed(r) for r in rows)
    return sorted(rows, key=lambda r: expected_ms(r["latency"], _speed(r), r.get("https") is True, typical,
                                                  r.get("streak")))


def _speed(row: dict) -> Optional[int]:
    value = row.get("speed_kbps")
    return value if type(value) is int and value > 0 else None
