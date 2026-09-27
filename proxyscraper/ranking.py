"""Which proxy is "fastest": how quickly a page comes through, not just the first answer (#186).

A quick answer to one tiny request says little about loading a page – in a test on the live list, the 25 HTTPS
proxies quickest to answer loaded 4 of 50 real pages, the first 25 ranked by answer plus the download speed of the
hourly speed step 26 of 50. Everything that orders proxies of the live list uses this: the published lists, the
pages, --pick, live_proxies, the rotating pool.
"""

from __future__ import annotations

import statistics
from typing import Iterable, List, Optional

PAGE_KB = 100               # roughly one page – the download the speed step measures
UNMEASURED_KBPS = 20        # tried in the speed step, no download got through: counted as slow (it passed the checks)


def page_ms(latency: float, speed_kbps: Optional[int], https: Optional[bool], typical_kbps: Optional[float]) -> float:
    """Roughly how long a page takes through a proxy: the first answer plus the download.

    typical_kbps is the median measured speed of the set, None when it has no speeds at all (an own scan) – then
    latency decides alone. The speed step only tries HTTPS-capable proxies: one of those without a speed didn't
    get the download through, the others were never tried and count as typical."""
    if not typical_kbps:
        return latency
    kbps = speed_kbps or (UNMEASURED_KBPS if https else typical_kbps)
    return latency + PAGE_KB * 1000 / kbps


def typical_speed(speeds: Iterable[Optional[int]]) -> Optional[float]:
    measured = [s for s in speeds if s]
    return statistics.median(measured) if measured else None


def best_first(rows: Iterable[dict]) -> List[dict]:
    """Rows of a run (dicts as in proxies.json), the fastest to load a page first."""
    rows = list(rows)
    typical = typical_speed(_speed(r) for r in rows)
    return sorted(rows, key=lambda r: page_ms(r["latency"], _speed(r), r.get("https") is True, typical))


def _speed(row: dict) -> Optional[int]:
    value = row.get("speed_kbps")
    return value if type(value) is int and value > 0 else None
