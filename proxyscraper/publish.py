"""Prepares the hits of a run for the `proxy-list` branch (runs in GitHub Actions).

    python -m proxyscraper.publish results/<run> public/ --min 20

Writes lists per protocol, HTTPS and elite lists, JSON/CSV, badge files for shields.io,
a README and the website for GitHub Pages (site/index.html plus history.json for the trend).
If there are fewer than `--min` hits (e.g. because the runner was unlucky), it exits with
code 78 and writes nothing – the old list then stays online.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from .parsing import PROXY_TYPES

SKIP_EXIT_CODE = 78
SITE = Path(__file__).resolve().parent / "site"  # index.html plus the images it links (logo, preview, touch icon)
HISTORY_LIMIT = 120  # 30 days with a run every 6 hours
RAW_BASE = "https://raw.githubusercontent.com/maximilianfeix/proxy-scraper/proxy-list"


def is_public(row: dict) -> bool:
    """Proxies with credentials never belong in the public list – the login comes from some
    third-party list, and once published it would be visible to everyone."""
    return "@" not in row.get("proxy", "")


def load_rows(run_dir: Path) -> List[dict]:
    rows = json.loads((run_dir / "proxies.json").read_text(encoding="utf-8"))
    return sorted((r for r in rows if is_public(r)), key=lambda r: r["latency"])


def num(n: int) -> str:
    """Thousands separators: 12345 -> 12,345"""
    return f"{n:,}"


def badge(label: str, count: int, color: str) -> dict:
    """Format for https://shields.io/badges/endpoint-badge"""
    return {"schemaVersion": 1, "label": label, "message": num(count), "color": color}


def stats_for(rows: List[dict], now: datetime) -> dict:
    return {
        "updated": now.isoformat(timespec="seconds"),
        "total": len(rows),
        "by_type": {t: sum(1 for r in rows if r["ptype"] == t) for t in PROXY_TYPES},
        "https": sum(1 for r in rows if r.get("https")),
        "elite": sum(1 for r in rows if r.get("anonymity") == "elite"),
        # only with provider data – otherwise "0" would wrongly mean "no datacenters"
        "datacenter": sum(1 for r in rows if r.get("hosting")) if any(r.get("org") for r in rows) else None,
        "stable": sum(1 for r in rows if r.get("streak", 0) >= STABLE_RUNS),
        "countries": dict(Counter(r["country"] for r in rows if r.get("country")).most_common(15)),
        "median_latency": round(statistics.median(r["latency"] for r in rows)) if rows else 0,
    }


def write_lists(rows: List[dict], out: Path) -> Dict[str, int]:
    files = {
        "all.txt": [r["url"] for r in rows],
        "https.txt": [r["url"] for r in rows if r.get("https")],
        "elite.txt": [r["url"] for r in rows if r.get("anonymity") == "elite"],
    }
    for t in PROXY_TYPES:
        files[f"{t}.txt"] = [r["proxy"] for r in rows if r["ptype"] == t]
    for name, lines in files.items():
        (out / name).write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")
    return {name: len(lines) for name, lines in files.items()}


def readme(stats: dict, counts: Dict[str, int]) -> str:
    updated = datetime.fromisoformat(stats["updated"]).strftime("%Y-%m-%d %H:%M UTC")
    rows = [
        ("All (`type://ip:port`)", "all.txt"),
        ("HTTP (`ip:port`)", "http.txt"),
        ("SOCKS4 (`ip:port`)", "socks4.txt"),
        ("SOCKS5 (`ip:port`)", "socks5.txt"),
        ("HTTPS-capable (`type://ip:port`)", "https.txt"),
        ("Elite (`type://ip:port`)", "elite.txt"),
    ]
    table = "\n".join(f"| {label} | {num(counts[name])} | [{name}]({RAW_BASE}/{name}) |" for label, name in rows)
    details = f"[proxies.json]({RAW_BASE}/proxies.json) · [proxies.csv]({RAW_BASE}/proxies.csv)"
    countries = " · ".join(f"{cc} {num(n)}" for cc, n in stats["countries"].items()) or "–"
    return f"""# Live proxy list

Generated automatically by [proxy-scraper](https://github.com/maximilianfeix/proxy-scraper) with GitHub Actions.
Every proxy here really worked in the last run – sorted by latency, fastest first.
Browse and filter it on the [website](https://maximilianfeix.github.io/proxy-scraper/).

**Updated:** {updated} · **{num(stats["total"])} proxies** · median latency {num(stats["median_latency"])} ms

| List | Count | File |
|---|---:|---|
{table}
| Details (latency, country, HTTPS, anonymity) | {num(stats["total"])} | {details} |

**Top countries:** {countries}

> Public proxies are run by strangers. Never send passwords or personal data through them.
"""


def step_summary(stats: dict) -> str:
    by_type = " · ".join(f"{t}: {n}" for t, n in stats["by_type"].items())
    return (f"### Proxy list updated\n\n**{stats['total']}** working proxies ({by_type}), "
            f"{stats['https']} HTTPS-capable, {stats['elite']} elite, median latency {stats['median_latency']} ms\n")


def write_json(path: Path, data, indent: Optional[int] = None) -> None:
    path.write_text(json.dumps(data, indent=indent, ensure_ascii=False), encoding="utf-8")


def load_history(path: Optional[Path]) -> List[dict]:
    """History of the last runs (fetched from the branch) – broken or missing means: start over."""
    if not path:
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    return [e for e in data if isinstance(e, dict) and isinstance(e.get("total"), int)]


def history_entry(stats: dict) -> dict:
    return {"updated": stats["updated"], "total": stats["total"], "https": stats["https"],
            "by_type": stats["by_type"], "median_latency": stats["median_latency"]}


STABLE_RUNS = 4  # this many runs in a row (= 24 hours with a run every 6 hours) means "stable"


def load_streaks(path: Optional[Path]) -> Dict[str, int]:
    """url -> runs in a row it has been on the list (fetched from the branch); broken or missing = start over."""
    if not path:
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {k: v for k, v in data.items() if isinstance(k, str) and type(v) is int and v > 0}  # bool is an int too


def publish(run_dir: Path, out: Path, minimum: int = 20, now: Optional[datetime] = None,
            history: Optional[Path] = None, streaks: Optional[Path] = None) -> int:
    rows = load_rows(run_dir)
    if len(rows) < minimum:
        print(f"Only {len(rows)} hits (< {minimum}) – the old list stays online.")
        return SKIP_EXIT_CODE
    now = now or datetime.now(timezone.utc)
    # whoever was there in the last run keeps counting – everyone else starts at 1, whoever is missing drops out
    previous = load_streaks(streaks)
    for row in rows:
        row["streak"] = previous.get(row["url"], 0) + 1
    out.mkdir(parents=True, exist_ok=True)
    counts = write_lists(rows, out)
    # don't just copy: rewrite the details so nothing with credentials ends up there either
    (out / "proxies.json").write_text(json.dumps(rows, indent=1, ensure_ascii=False), encoding="utf-8")
    with (run_dir / "proxies.csv").open(newline="", encoding="utf-8") as src, \
            (out / "proxies.csv").open("w", newline="", encoding="utf-8") as dst:
        reader = csv.DictReader(src)
        writer = csv.DictWriter(dst, fieldnames=reader.fieldnames or ["proxy"])
        writer.writeheader()
        writer.writerows(r for r in reader if is_public(r))
    stats = stats_for(rows, now)
    write_json(out / "stats.json", stats, indent=1)
    badges = out / "badges"
    badges.mkdir(exist_ok=True)
    colors = {"total": "brightgreen", "http": "blue", "socks4": "blueviolet", "socks5": "green"}
    write_json(badges / "total.json", badge("working proxies", stats["total"], colors["total"]))
    for t in PROXY_TYPES:
        write_json(badges / f"{t}.json", badge(t, stats["by_type"][t], colors[t]))
    write_json(badges / "updated.json", {"schemaVersion": 1, "label": "updated",
                                         "message": now.strftime("%Y-%m-%d %H:%M UTC"), "color": "grey"})
    (out / "README.md").write_text(readme(stats, counts), encoding="utf-8")
    # website: a static page that loads proxies.json/stats.json/history.json from next door
    for asset in SITE.iterdir():
        if asset.suffix in (".html", ".png"):
            (out / asset.name).write_bytes(asset.read_bytes())
    (out / ".nojekyll").write_text("", encoding="utf-8")  # Pages should serve the files unchanged
    runs = [*load_history(history), history_entry(stats)][-HISTORY_LIMIT:]
    write_json(out / "history.json", runs)
    write_json(out / "streaks.json", {row["url"]: row["streak"] for row in rows})

    summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_file:
        with open(summary_file, "a", encoding="utf-8") as fh:
            fh.write(step_summary(stats))
    print(f"{stats['total']} proxies written to {out}.")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="prepare the hits of a run for the proxy-list branch")
    p.add_argument("run_dir", type=Path)
    p.add_argument("out_dir", type=Path)
    p.add_argument("--min", type=int, default=20, help="at least this many hits, otherwise write nothing")
    p.add_argument("--history", type=Path, help="history.json from last time (for the chart on the website)")
    p.add_argument("--streaks", type=Path, help="streaks.json from last time (how long each proxy has been listed)")
    args = p.parse_args(argv)
    return publish(args.run_dir, args.out_dir, args.min, history=args.history, streaks=args.streaks)


if __name__ == "__main__":
    sys.exit(main())
