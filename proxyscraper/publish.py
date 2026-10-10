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
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Dict, List, Optional

from .charts import THEMES, countries_svg, trend_svg
from .exporters import pac
from .pages import write_pages
from .parsing import PROXY_TYPES
from .proxypages import write_proxy_pages
from .ranking import best_first
from .report import weekly_facts, write_report
from .sites import SITES
from .sourcepages import write_source_pages
from .sources import SourceStats

SKIP_EXIT_CODE = 78
SITE = Path(__file__).resolve().parent / "site"  # index.html plus the images it links (logo, preview, touch icon)
RUN_HOURS = 1  # the proxy-list workflow runs every hour; clients read it from stats.json as run_hours
HISTORY_LIMIT = 30 * 24 // RUN_HOURS  # 30 days of runs for the chart
RAW_BASE = "https://raw.githubusercontent.com/maximilianfeix/proxy-scraper/proxy-list"


def is_public(row: dict) -> bool:
    """Proxies with credentials never belong in the public list – the login comes from some
    third-party list, and once published it would be visible to everyone."""
    return "@" not in row.get("proxy", "")


def load_rows(run_dir: Path) -> List[dict]:
    rows = json.loads((run_dir / "proxies.json").read_text(encoding="utf-8"))
    return best_first(r for r in rows if is_public(r))


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
        # only when the lookup ran – otherwise "0" would wrongly mean "none listed"
        "blocklisted": sum(1 for r in rows if r.get("blocklisted"))
        if any(r.get("blocklisted") is not None for r in rows) else None,
        "stable": sum(1 for r in rows if r.get("streak", 0) >= STABLE_RUNS),
        # proxies that got through to Google, Reddit, ... in the site check after the run (sites.py)
        # None when a site wasn't checked at all (the step failed, its DNS lookup didn't work) – not a measured 0
        "sites": {s.name: sum(1 for r in rows if (r.get("sites") or {}).get(s.name))
                  if any(s.name in (r.get("sites") or {}) for r in rows) else None for s in SITES},
        "run_hours": RUN_HOURS,
        "countries": dict(Counter(r["country"] for r in rows if r.get("country")).most_common(15)),
        "median_latency": round(statistics.median(r["latency"] for r in rows)) if rows else 0,
        # download speed of the HTTPS-capable ones (speed.py), None when it wasn't measured
        "median_speed_kbps": round(statistics.median(speeds)) if (speeds := [r["speed_kbps"] for r in rows
                                                                               if r.get("speed_kbps")]) else None,
    }


def write_lists(rows: List[dict], out: Path) -> Dict[str, int]:
    files = {
        "all.txt": [r["url"] for r in rows],
        "https.txt": [r["url"] for r in rows if r.get("https")],
        "elite.txt": [r["url"] for r in rows if r.get("anonymity") == "elite"],
        "stable.txt": [r["url"] for r in rows if (r.get("uptime_7d") or 0) >= STABLE_UPTIME],
    }
    for t in PROXY_TYPES:
        files[f"{t}.txt"] = [r["proxy"] for r in rows if r["ptype"] == t]
    for site in SITES:
        files[f"works-with/{site.name}.txt"] = [r["url"] for r in rows if (r.get("sites") or {}).get(site.name)]
    (out / "works-with").mkdir(exist_ok=True)
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
        (f"Stable, listed in {STABLE_UPTIME} %+ of the runs this week (`type://ip:port`)", "stable.txt"),
    ]
    table = "\n".join(f"| {label} | {num(counts[name])} | [{name}]({RAW_BASE}/{name}) |" for label, name in rows)
    details = f"[proxies.json]({RAW_BASE}/proxies.json) · [proxies.csv]({RAW_BASE}/proxies.csv)"
    countries = " · ".join(f"{cc} {num(n)}" for cc, n in stats["countries"].items()) or "–"
    return f"""# Live proxy list

Generated automatically by [proxy-scraper](https://github.com/maximilianfeix/proxy-scraper) with GitHub Actions.
Every proxy here really worked in the last run – best first: by first answer plus the download speed measured
right after the run, and by how likely it is to still be up (a proxy that has been listed for a day almost always is,
a new one only in 1 of 4 cases).
Browse and filter it on the [website](https://maximilianfeix.github.io/proxy-scraper/), or get the lists alone,
one per country too, from [free-proxy-list](https://github.com/maximilianfeix/free-proxy-list).

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
            "by_type": stats["by_type"], "median_latency": stats["median_latency"], "run_hours": RUN_HOURS}


def streak_factor(runs: List[dict]) -> int:
    """Old streaks count runs of the previous interval: entries from before run_hours existed ran every 6 hours.
    Multiplying keeps "up for 5 days" at 5 days when the interval gets shorter."""
    if not runs:
        return 1
    before = runs[-1].get("run_hours", 6)
    return max(1, before // RUN_HOURS) if type(before) is int and before > 0 else 1


STABLE_RUNS = 24 // RUN_HOURS  # this many runs in a row (= 24 hours) means "stable"


UPTIME_RUNS = 7 * 24 // RUN_HOURS  # uptime looks back a week
STABLE_UPTIME = 90                  # listed in this share of the week's runs -> stable.txt
MIN_UPTIME_RUNS = 24 // RUN_HOURS   # while the history is younger than a day, missing runs count as not listed


def load_seen(path: Optional[Path], last_run: Optional[str]) -> Optional[Dict[str, dict]]:
    """url -> {first_seen, bits} from last time. bits: one per run, bit 0 = the last run. None when missing,
    broken or written after a different run than the last one in the history - then the bits wouldn't line up."""
    if not path or not last_run:
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("last_run") != last_run or not isinstance(data.get("proxies"), dict):
        return None
    seen = {}
    for url, entry in data["proxies"].items():
        try:
            seen[url] = {"first_seen": str(entry["first_seen"]), "bits": int(entry["bits"], 16)}
        except (KeyError, TypeError, ValueError):
            continue
    return seen


def update_seen(rows: List[dict], seen: Optional[Dict[str, dict]], now: datetime) -> Dict[str, dict]:
    """Shift everyone by one run and mark who is listed now. Without usable data from last time, the
    streaks stand in: a proxy listed n runs in a row was there for the last n runs."""
    mask = (1 << UPTIME_RUNS) - 1
    stamp = now.isoformat(timespec="seconds")
    if seen is None:
        since = {r["url"]: now - timedelta(hours=(r["streak"] - 1) * RUN_HOURS) for r in rows}
        seen = {r["url"]: {"first_seen": since[r["url"]].isoformat(timespec="seconds"),
                           "bits": ((1 << min(r["streak"], UPTIME_RUNS)) - 1) >> 1}  # this run is added below
                for r in rows}
    listed = {r["url"] for r in rows}
    fresh = {}
    for url, entry in seen.items():
        bits = ((entry["bits"] << 1) | (url in listed)) & mask
        if bits:
            fresh[url] = {"first_seen": entry["first_seen"], "bits": bits}
    for url in listed - fresh.keys():
        fresh[url] = {"first_seen": stamp, "bits": 1}
    return fresh


def uptime(bits: int, runs: List[dict], now: datetime, hours: int) -> int:
    """Share of the runs in the last `hours` this proxy was listed in, in percent. runs: oldest first, this one last."""
    since = now - timedelta(hours=hours)
    window = 0
    for run in reversed(runs[-UPTIME_RUNS:]):
        try:
            when = datetime.fromisoformat(run["updated"])
        except (KeyError, TypeError, ValueError):
            break
        if when <= since:
            break
        window += 1
    # a young history (new fork, lost history.json) must not turn one good run into 100 %
    window = max(window, min(MIN_UPTIME_RUNS, hours // RUN_HOURS))
    return round(100 * bin(bits & ((1 << window) - 1)).count("1") / window)


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
            history: Optional[Path] = None, streaks: Optional[Path] = None, seen: Optional[Path] = None,
            feed: Optional[Path] = None, sources: Optional[Path] = None) -> int:
    rows = load_rows(run_dir)
    if len(rows) < minimum:
        print(f"Only {len(rows)} hits (< {minimum}) – the old list stays online.")
        return SKIP_EXIT_CODE
    now = now or datetime.now(timezone.utc)
    # whoever was there in the last run keeps counting – everyone else starts at 1, whoever is missing drops out
    past_runs = load_history(history)
    factor = streak_factor(past_runs)
    previous = {url: n * factor for url, n in load_streaks(streaks).items()}
    for row in rows:
        row["streak"] = previous.get(row["url"], 0) + 1
    rows = best_first(rows)  # again, now that the streaks say who is likely to last
    runs = [*past_runs, history_entry(stats_for(rows, now))][-HISTORY_LIMIT:]
    listed = update_seen(rows, load_seen(seen, past_runs[-1].get("updated") if past_runs else None), now)
    for row in rows:
        entry = listed[row["url"]]
        row["first_seen"] = entry["first_seen"]
        row["uptime_24h"] = uptime(entry["bits"], runs, now, 24)
        row["uptime_7d"] = uptime(entry["bits"], runs, now, 7 * 24)
    out.mkdir(parents=True, exist_ok=True)
    counts = write_lists(rows, out)
    # one URL for a browser's proxy settings – the same proxies, best first, as a PAC file
    pac_rows = [SimpleNamespace(ptype=r["ptype"], proxy=r["proxy"], https=r.get("https")) for r in rows]
    (out / "proxy.pac").write_text(pac(pac_rows, now), encoding="utf-8")
    # don't just copy: rewrite the details so nothing with credentials ends up there either
    (out / "proxies.json").write_text(json.dumps(rows, indent=1, ensure_ascii=False), encoding="utf-8")
    with (run_dir / "proxies.csv").open(newline="", encoding="utf-8") as src, \
            (out / "proxies.csv").open("w", newline="", encoding="utf-8") as dst:
        reader = csv.DictReader(src)
        extra = ("first_seen", "uptime_24h", "uptime_7d", "works_with", "speed_kbps")
        base = list(reader.fieldnames or ["proxy"])
        writer = csv.DictWriter(dst, fieldnames=[*base, *(k for k in extra if k not in base)])
        writer.writeheader()
        csv_rows = {r.get("url", ""): r for r in reader if is_public(r)}
        for listed_row in rows:  # in the order of proxies.json: best first
            r = csv_rows.get(listed_row.get("url", ""))
            if r is not None:
                works = " ".join(name for name, ok in (listed_row.get("sites") or {}).items() if ok)
                writer.writerow({**r, **{k: listed_row.get(k, "") for k in extra}, "works_with": works})
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
    # a page per proxy (with its week as a timeline), then the pages per protocol and country plus sitemap.xml
    try:
        run_times = [datetime.fromisoformat(run["updated"]) for run in runs[-UPTIME_RUNS:]]
    except (KeyError, TypeError, ValueError):
        run_times = []  # a broken entry: no timeline rather than one whose cells don't match the times
    timelines = {url: e["bits"] for url, e in listed.items()} if run_times else {}
    current = {r["url"] for r in rows}
    gone = {url: (e["bits"], uptime(e["bits"], runs, now, 7 * 24), e["first_seen"])
            for url, e in listed.items() if url not in current} if run_times else {}
    proxy_pages = write_proxy_pages(rows, out, now, timelines, run_times, gone=gone)
    # which lists the proxies came from: the learned source statistics as a ranking (sourcepages.py)
    quality = SourceStats(sources) if sources is not None and sources.exists() else None
    write_pages(rows, out, now, extra=[*write_source_pages(quality, out, now), *proxy_pages])
    write_json(out / "history.json", runs)
    # the weekly report: lifetimes, sites, countries – a page, markdown and a short post (report.py)
    write_report(weekly_facts(rows, runs, {url: e["bits"] for url, e in listed.items()}, now), out, previous_feed=feed)
    for theme in THEMES:  # charts for the README, which embeds them from GitHub Pages
        (out / f"chart-{theme}.svg").write_text(trend_svg(runs, now, theme), encoding="utf-8")
        (out / f"countries-{theme}.svg").write_text(countries_svg(stats["countries"], theme), encoding="utf-8")
    write_json(out / "seen.json", {"last_run": runs[-1]["updated"],
                                   "proxies": {url: {"first_seen": e["first_seen"], "bits": format(e["bits"], "x")}
                                               for url, e in listed.items()}})
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
    p.add_argument("--seen", type=Path,
                   help="seen.json from last time (which runs each proxy was listed in, for the uptime)")
    p.add_argument("--feed", type=Path, help="report/feed.xml from last time (the weekly entries it keeps)")
    p.add_argument("--sources", type=Path,
                   help="data/source_stats.json of this run (for the ranking of the sources on the website)")
    args = p.parse_args(argv)
    return publish(args.run_dir, args.out_dir, args.min, history=args.history, streaks=args.streaks, seen=args.seen,
                   feed=args.feed, sources=args.sources)


if __name__ == "__main__":
    sys.exit(main())
