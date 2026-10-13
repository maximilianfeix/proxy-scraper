"""The funnel of the hourly runs, from the console logs of the "proxy list" workflow.

    gh run list --workflow "proxy list" --limit 60 --json databaseId,createdAt   # pick the runs
    gh run view <id> --log > logs/<createdAt>.log                                # one file per run
    python docs/analysis/funnel_from_logs.py logs/ > docs/analysis/data/runs.csv

One CSV row per run, read from what the run printed: how many unique candidates the lists held, how many of them
were checked (the workflow's --limit), and how many ended where. The logs are the only place these numbers exist
for runs before 1.29 – GitHub deletes them after 90 days, which is why the result is kept in data/.
From 1.29 on every run writes the same numbers, with reasons, to run.json (see docs/check-states.md).

What a row can and cannot say:
  unique_candidates       protocol/address combinations (an ip:port listed as http and socks5 counts twice)
  checked_limit           the most promising N of them – proxies that passed before and good sources first
  second_request_failed   answered the first request, not confirmed by the second. Why is not in the logs
  content_differed        confirmed, but the test page's hash differed. Why is not in the logs either
  kept                    passed all three
"""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

FIELDS = ["run_started", "unique_candidates", "checked_limit", "known_from_history", "kept", "second_request_failed",
          "content_differed", "answered", "check_target_switched", "second_target_missing"]
STARTED = re.compile(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})")


def number(pattern: str, text: str):
    m = re.search(pattern, text)
    return int(m.group(1).replace(",", "")) if m else None


def parse(text: str) -> dict:
    started = STARTED.search(text)
    kept = number(r"│ WORKING[^\n]*\n[^│\n]*│ ([\d,]+)", text)  # the first card of the final summary
    failed = number(r"([\d,]+) fakes", text) or 0
    differed = number(r"([\d,]+) prox(?:y|ies) modified a test page", text) or 0
    return {
        "run_started": started.group(1) + "Z" if started else "",
        "unique_candidates": number(r"Collected\s+([\d,]+) unique", text),
        "checked_limit": number(r"checking the ([\d,]+) most", text),
        "known_from_history": number(r"History\s+([\d,]+) proxies", text),
        "kept": kept,
        "second_request_failed": failed,
        "content_differed": differed,
        "answered": None if kept is None else kept + failed + differed,
        "check_target_switched": int("Check target went down" in text),
        "second_target_missing": int("without a second confirmation" in text),
    }


def main(folder: str) -> int:
    rows = [parse(path.read_text(encoding="utf-8", errors="replace")) for path in sorted(Path(folder).glob("*.log"))]
    rows = sorted((r for r in rows if r["kept"] is not None), key=lambda r: r["run_started"])
    writer = csv.DictWriter(sys.stdout, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return 0 if rows else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "."))
