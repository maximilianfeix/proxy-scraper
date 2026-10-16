"""Totals and shares of the funnel, with every denominator spelled out.

    python docs/analysis/funnel_summary.py docs/analysis/data/runs-2026-09-28_29.csv [FROM] [TO]

FROM and TO are run start times as in the file (inclusive), to look at a window of the runs.
"""

from __future__ import annotations

import csv
import statistics
import sys


def pct(part: float, whole: float) -> str:
    return f"{100 * part / whole:.1f} %" if whole else "–"


def main(path: str, first: str = "", last: str = "9") -> int:
    with open(path, newline="", encoding="utf-8") as fh:
        rows = [{k: (int(v) if v.isdigit() else v) for k, v in row.items()} for row in csv.DictReader(fh)]
    rows = [r for r in rows if first <= r["run_started"] <= last]
    checks = sum(r["checked_limit"] for r in rows)
    kept = sum(r["kept"] for r in rows)
    failed = sum(r["second_request_failed"] for r in rows)
    differed = sum(r["content_differed"] for r in rows)
    answered = kept + failed + differed
    print(f"runs                         {len(rows)}  ({rows[0]['run_started']} … {rows[-1]['run_started']})")
    print(f"unique candidates per run    mean {round(statistics.mean(r['unique_candidates'] for r in rows)):,} "
          "(protocol/address combinations)")
    print(f"checks                       {checks:,}  = sum of the per-run limit; repeats of a prioritised sample, "
          "not distinct proxies")
    print(f"answered the first request   {answered:,}  = {pct(answered, checks)} of checks")
    print(f"second request not passed    {failed:,}  = {pct(failed, answered)} of answered "
          f"(per run {pct(min(r['second_request_failed'] / r['answered'] for r in rows), 1)} … "
          f"{pct(max(r['second_request_failed'] / r['answered'] for r in rows), 1)})")
    reached = kept + differed
    print(f"reached the content check    {reached:,}")
    print(f"test page's hash differed    {differed:,}  = {pct(differed, reached)} of those that reached it, "
          f"{pct(differed, answered)} of answered; {differed / len(rows):.0f} per run")
    print(f"kept                         {kept:,}  = {pct(kept, checks)} of checks, {pct(kept, answered)} of answered")
    print(f"runs with a check target switch: {sum(r['check_target_switched'] for r in rows)}, "
          f"without a second target: {sum(r['second_target_missing'] for r in rows)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:4]))
