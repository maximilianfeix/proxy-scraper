"""How long entries stay on the hourly list – from the files the list publishes about itself.

    git fetch origin proxy-list && mkdir -p list
    for f in history.json seen.json proxies.json; do git show origin/proxy-list:$f > list/$f; done
    python docs/analysis/list_churn.py list/

seen.json holds, per type://ip:port entry, one bit per published run of the last week: on the list or not.
That is all there is, so this is all the numbers below can mean:

  - "on the list" = passed the first request, the second request and the content check in that run.
    "Not on the list" has no recorded reason: the entry may
    have failed, may not have been reached within the run's limit of 150,000 checks, or the second check
    target may have been unavailable. Before 1.29 none of these were told apart.
  - An entry is one protocol and one ip:port. Many entries are ports of the same machine, so every number is
    given per entry and per host.
  - Runs are about hourly, not exactly; "24 runs" is roughly a day.
"""

from __future__ import annotations

import json
import statistics
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

DAY_RUNS = 24


def host(url: str) -> str:
    return url.split("://", 1)[1].rsplit(":", 1)[0]


def ended_stretch(bits: int, runs: int) -> Optional[int]:
    """Runs in a row of the last stretch on the list, for entries that are off it again and whose stretch began
    inside the window. Entries still listed have no ended stretch – they are counted separately."""
    bits &= (1 << runs) - 1
    if not bits or bits & 1:
        return None
    low = (bits & -bits).bit_length() - 1
    length = 0
    while low + length < runs and bits >> (low + length) & 1:
        length += 1
    return None if low + length >= runs else length


def all_ended_stretches(bits: int, runs: int) -> List[int]:
    """The length of every stretch on the list that began and ended inside the window – an entry that came and
    went five times has five. (ended_stretch above looks only at the last one, and only if the entry is off the
    list now: that is how the weekly report counts.)"""
    lengths, length = [], 0
    for t in range(runs - 1, -1, -1):  # oldest run first
        if bits >> t & 1:
            length += 1
        else:
            if length and length != runs - 1 - t:  # not one that was already running when the window began
                lengths.append(length)
            length = 0
    return lengths  # a stretch that reaches the newest run hasn't ended


def current_stretch(bits: int, runs: int) -> int:
    n = 0
    while n < runs and bits >> n & 1:
        n += 1
    return n


def stretches(seen: Dict[str, int], runs: int, label: str) -> None:
    mask = (1 << runs) - 1
    ended = [n for bits in seen.values() if (n := ended_stretch(bits, runs))]
    one = sum(1 for n in ended if n == 1)
    every = [n for bits in seen.values() for n in all_ended_stretches(bits, runs)]
    every_one = sum(1 for n in every if n == 1)
    print(f"{label}")
    print(f"  on the list at least once        {sum(1 for b in seen.values() if b & mask):,}")
    print(f"  off the list at the end          {len(ended):,}  (counted by their last stretch, like the weekly report)")
    print(f"    last stretch one run long      {one:,}  = {100 * one / max(len(ended), 1):.0f} % of those")
    print(f"    last stretch {DAY_RUNS}+ runs long     {sum(1 for n in ended if n >= DAY_RUNS):,}")
    print(f"  every stretch that began and ended inside the window: {len(every):,}")
    print(f"    one run long                   {every_one:,}  = {100 * every_one / max(len(every), 1):.0f} % of those")
    print(f"    {DAY_RUNS}+ runs long                  {sum(1 for n in every if n >= DAY_RUNS):,}")
    print(f"  still listed, for {DAY_RUNS}+ runs now   "
          f"{sum(1 for b in seen.values() if current_stretch(b, runs) >= DAY_RUNS):,}  (not part of the ended ones)")


def retention(seen: Dict[str, int], runs: int, lag: int) -> List[float]:
    """Per run: the share of that run's list that is on the list again `lag` runs later."""
    shares = []
    for t in range(lag, runs):  # bit t = listed t runs ago
        listed = [bits for bits in seen.values() if bits >> t & 1]
        if listed:
            shares.append(100 * sum(1 for bits in listed if bits >> (t - lag) & 1) / len(listed))
    return shares


def main(folder: str) -> int:
    base = Path(folder)
    history = json.loads((base / "history.json").read_text(encoding="utf-8"))
    raw = json.loads((base / "seen.json").read_text(encoding="utf-8"))
    seen = {url: int(entry["bits"], 16) for url, entry in raw["proxies"].items()}
    now = datetime.fromisoformat(history[-1]["updated"])
    window = [r for r in history if datetime.fromisoformat(r["updated"]) > now - timedelta(days=7)]
    runs = len(window)
    times = [datetime.fromisoformat(r["updated"]) for r in window]
    gaps = [(b - a).total_seconds() / 3600 for a, b in zip(times, times[1:])]

    print(f"window     {window[0]['updated']} … {window[-1]['updated']}: {runs} published runs")
    print(f"gaps       median {statistics.median(gaps):.2f} h, longest {max(gaps):.1f} h, "
          f"{sum(1 for g in gaps if g > 1.5)} over 1.5 h")
    hosts = Counter(host(url) for url in seen)
    crowded = {h for h, n in hosts.items() if n >= 50}
    print(f"entries    {len(seen):,} type://ip:port entries on {len(hosts):,} hosts; "
          f"{sum(hosts[h] for h in crowded):,} of them ({100 * sum(hosts[h] for h in crowded) / len(seen):.0f} %) "
          f"are ports on {len(crowded)} hosts with 50+ entries each")
    print()
    stretches(seen, runs, "per entry")
    stretches({u: b for u, b in seen.items() if host(u) not in crowded}, runs, "per entry, without the crowded hosts")
    per_host: Dict[str, int] = {}
    for url, bits in seen.items():  # a host is on the list in a run if any of its entries is
        per_host[host(url)] = per_host.get(host(url), 0) | bits
    stretches(per_host, runs, "per host")
    print()
    for lag in (1, DAY_RUNS):
        for label, part in (("all entries", seen), ("without the crowded hosts",
                                                   {u: b for u, b in seen.items() if host(u) not in crowded})):
            shares = retention(part, runs, lag)
            print(f"of a run's list, on the list again {lag:>2} run(s) later ({label}): median "
                  f"{statistics.median(shares):.0f} %, range {min(shares):.0f}–{max(shares):.0f} % "
                  f"over {len(shares)} runs")
    rows_path = base / "proxies.json"
    if rows_path.exists():
        rows = json.loads(rows_path.read_text(encoding="utf-8"))
        print()
        print(f"current list: {len(rows):,} entries, {len({r['proxy'] for r in rows}):,} ip:port, "
              f"{len({host(r['url']) for r in rows}):,} hosts, {len({r.get('exit_ip') for r in rows}):,} exit IPs")
        with_checks = sum(1 for r in rows if r.get("checks"))
        print(f"entries that carry per-check states (1.29+): {with_checks:,}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "."))
