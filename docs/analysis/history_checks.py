"""What the checks of the published runs ended as – from the list's own history.

    git fetch origin proxy-list && mkdir -p list
    git show origin/proxy-list:history.json > list/history.json
    python docs/analysis/history_checks.py list/history.json

history.json keeps one entry per published run. Runs from 1.30.0 on carry a `checks` object:
per check (basic, confirm, content, https) a counter per `state:reason`. Nothing else about a
run is stored, so this is all these numbers can mean:

  - They are counts of *checks*, not of distinct proxies. The same address is checked again in
    every run it is a candidate for, and the most promising candidates go first every hour, so
    the runs overlap heavily. "19.8 million checks" is not 19.8 million machines.
  - A check only happens if the one before it passed, so each step's denominator is the step
    before it. Percentages below are always of that step, and it is named.
  - `unavailable` means the check could not be measured (the target did not answer); it is not
    a statement about the proxy.
  - A reason code says what the measurement saw, never why. `exit_ip_mismatch` can be a
    rotating exit pool as easily as a proxy faking the first answer.
"""
from __future__ import annotations

import collections
import json
import sys
from typing import Dict, List

CHECKS = ("basic", "confirm", "content", "https")


def runs_with_checks(history: object) -> List[dict]:
    entries = history if isinstance(history, list) else history.get("runs", [])
    return [r for r in entries if isinstance(r, dict) and r.get("checks")]


def aggregate(runs: List[dict]) -> Dict[str, collections.Counter]:
    totals: Dict[str, collections.Counter] = {c: collections.Counter() for c in CHECKS}
    for run in runs:
        for check, counts in run["checks"].items():
            if check in totals:
                totals[check].update(counts)
    return totals


def main(argv: List[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    with open(argv[1], encoding="utf-8") as fh:
        runs = runs_with_checks(json.load(fh))
    if not runs:
        print("no run in this history carries per-check counters (needs 1.30.0 or newer)")
        return 1

    first, last = runs[0].get("updated", "?"), runs[-1].get("updated", "?")
    candidates = sum(r.get("candidates", 0) for r in runs)
    print(f"{len(runs)} published runs, {first} -> {last}")
    print(f"{candidates:,} candidates checked in total (the same address recurs across runs)\n")

    totals = aggregate(runs)
    for check in CHECKS:
        counts = totals[check]
        n = sum(counts.values())
        if not n:
            continue
        print(f"{check}: {n:,} checks")
        for reason, value in counts.most_common():
            print(f"    {reason:<34} {value:>12,}  {value / n * 100:5.2f}% of this step")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
