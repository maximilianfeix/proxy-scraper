"""Which free proxy lists actually work: a public ranking of the sources, rewritten with every run.

The tool learns per source how many of its proxies pass the checks (sources.py). The hourly run publishes
that as a page and as sources.json: every list by the number of working proxies it delivered and by the share
of its proxies that worked. The files of one repository count as one source.
"""

from __future__ import annotations

import json
import statistics
from collections import Counter
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlsplit

from .pages import CSS, PAGE_CSS, REPO_URL, SITE_URL
from .sources import DECAY, GH_RAW, SourceRecord, SourceStats

ROWS = 100         # sources in the main table – sources.json has all of them
BEST_ROWS = 25
MIN_CHECKED = 300  # fewer proxies checked per run than this say too little for the table of the best shares
OWN = "maximilianfeix/"  # our own lists are the result of these checks, so they don't belong in the ranking


def publisher(url: str) -> Tuple[str, str]:
    """(name, link) of who publishes a list: owner/repo for a file on GitHub, the host for anything else."""
    if url.startswith(GH_RAW + "/"):
        parts = url[len(GH_RAW) + 1:].split("/")
        if len(parts) >= 2 and parts[0] and parts[1]:
            name = f"{parts[0]}/{parts[1]}"
            return name, f"https://github.com/{name}"
    host = urlsplit(url).hostname or url
    return (host[4:] if host.startswith("www.") else host), f"https://{host}/"


def _per_run(rec: SourceRecord) -> Tuple[float, float]:
    """(checked, working) of an average recent run: the statistics keep sums in which every older run counts
    DECAY times as much, so they are divided by the weight of the runs they hold."""
    weight = (1 - DECAY ** rec.runs) / (1 - DECAY)
    return rec.checked / weight, rec.working / weight


def rank(quality: SourceStats, now: datetime) -> List[dict]:
    """Every source that was checked at least once, the one with the most working proxies first."""
    groups: Dict[str, dict] = {}
    for url, rec in quality.records.items():
        if not rec.runs or not rec.checked:
            continue
        name, link = publisher(url)
        if name.startswith(OWN):
            continue
        checked, working = _per_run(rec)
        group = groups.setdefault(name, {"name": name, "url": link, "lists": 0, "listed": 0, "checked": 0.0,
                                         "working": 0.0, "reasons": Counter(), "last_change": 0.0})
        group["lists"] += 1
        group["listed"] += rec.count
        group["checked"] += checked
        group["working"] += working
        group["reasons"][quality.skip_reason(url, now.timestamp()) or "active"] += 1
        group["last_change"] = max(group["last_change"], rec.last_change)
    ranking = []
    for group in groups.values():
        reasons = group.pop("reasons")
        changed = group["last_change"]
        ranking.append({
            **group,
            "share": round(100 * group["working"] / group["checked"], 1) if group["checked"] else 0.0,
            "checked": round(group["checked"]),
            "working": round(group["working"]),
            # the best of its files decides: one maintained file is enough for the source to count as alive,
            # and it is only dead when every file is
            "status": next(s for s in (*STATUS, *reasons) if reasons[s]),
            "last_change": (datetime.fromtimestamp(changed, timezone.utc).isoformat(timespec="seconds")
                            if changed else None),
        })
    return sorted(ranking, key=lambda s: (-s["working"], -s["share"], s["name"]))


# status of a file (SourceStats.skip_reason) -> what the page says, best first
STATUS = {"active": "maintained", "outdated": "unchanged for a week", "unreachable": "doesn't load",
          "dead": "nothing works"}

SOURCE_CSS = """
td.num, th.num { text-align: right; }
td .muted { color: var(--muted); }
.method p { color: var(--muted); max-width: 70ch; margin: 0 0 12px; }
"""


def _table(caption: str, sources: List[dict]) -> str:
    def row(i: int, s: dict) -> str:
        note = STATUS.get(s["status"], s["status"])
        status = "" if s["status"] == "active" else f' <span class="muted">· {note}</span>'
        return (f'<tr><td class="num">{i}</td><td><a href="{escape(s["url"], quote=True)}" rel="nofollow noopener">'
                f'{escape(s["name"])}</a>{status}</td><td class="num">{s["listed"]:,}</td>'
                f'<td class="num">{s["checked"]:,}</td><td class="num">{s["working"]:,}</td>'
                f'<td class="num">{s["share"]:.1f} %</td></tr>')

    rows = "\n".join(row(i, s) for i, s in enumerate(sources, 1))
    return (f'<div class="table"><table><caption>{escape(caption)}</caption><thead><tr>'
            '<th scope="col" class="num">#</th><th scope="col">Source</th>'
            '<th scope="col" class="num">Proxies listed</th>'
            '<th scope="col" class="num">Checked</th><th scope="col" class="num">Passed every check</th>'
            f'<th scope="col" class="num">Share</th></tr></thead><tbody>{rows}</tbody></table></div>')


def page(ranking: List[dict], updated: datetime) -> str:
    root = "../"
    when = updated.strftime("%d %b %Y, %H:%M UTC")
    # the share of a typical source. Not the sum over all of them: a working proxy is carried by many lists
    # and a dead one by few, so adding the sources up would count the good proxies many times over
    typical = statistics.median(s["share"] for s in ranking)
    alive = sum(s["status"] == "active" for s in ranking)
    empty = sum(not s["working"] for s in ranking)
    best = sorted((s for s in ranking if s["checked"] >= MIN_CHECKED and s["working"]),
                  key=lambda s: (-s["share"], -s["working"], s["name"]))[:BEST_ROWS]
    title = "Which free proxy lists actually work?"
    description = (f"{len(ranking):,} sources of free proxies, checked every hour. In a typical one "
                   f"{typical:.1f} % of the proxies pass a real handshake, a honeypot check and a content check. "
                   "Ranked by working proxies and by share.")
    lede = (f"{len(ranking):,} public sources of free proxies are collected and checked every hour. In the latest "
            f"runs a typical source had {typical:.1f} % of its checked proxies pass every check. This is how each "
            f"one did ({when}).")
    best_html = "" if not best else (
        "<section><h2>Highest share of working proxies</h2>"
        + _table(f"Highest share among the sources with at least {MIN_CHECKED:,} proxies checked per run.", best)
        + "</section>")
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} {len(ranking):,} sources ranked every hour | proxy-scraper</title>
<meta name="description" content="{escape(description)}">
<link rel="canonical" href="{SITE_URL}sources/">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{escape(description)}">
<meta property="og:image" content="{SITE_URL}og.png">
<meta property="og:url" content="{SITE_URL}sources/">
<meta name="twitter:card" content="summary_large_image">
<link rel="icon" href="{root}logo.png">
<link rel="apple-touch-icon" href="{root}apple-touch-icon.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Geist:wght@400..700&family=Geist+Mono:wght@400;500&display=swap"
      rel="stylesheet">
<style>{CSS}{PAGE_CSS}{SOURCE_CSS}</style>
</head>
<body>
<div class="wrap">
  <header>
    <a class="brand" href="{root}"><img src="{root}logo.png" alt="">proxy-scraper</a>
    <a href="{root}#list">The live list</a>
  </header>
  <main>
    <h1>{title}</h1>
    <p class="lede">{escape(lede)}</p>
    <div class="actions">
      <a class="btn primary" href="{root}#list">The proxies that passed</a>
      <a class="btn" href="{root}sources.json">All sources as JSON</a>
      <a class="btn" href="{REPO_URL}/issues/new?template=new_source.yml">Add a list</a>
    </div>
  </main>
  <dl class="facts">
    <div><dt>{len(ranking):,}</dt><dd>sources checked</dd></div>
    <div><dt>{alive:,}</dt><dd>still maintained</dd></div>
    <div><dt>{empty:,}</dt><dd>without a single working proxy</dd></div>
    <div><dt>{typical:.1f} %</dt><dd>work in a typical source (median)</dd></div>
  </dl>
  <section><h2>Most working proxies</h2>
  {_table(f"The {min(len(ranking), ROWS):,} sources that delivered the most working proxies per run.", ranking[:ROWS])}
  </section>
  {best_html}
  <section class="method"><h2>How it's counted</h2>
    <p>Every hour each list is downloaded and its proxies are checked: a real HTTP, SOCKS4 or SOCKS5 handshake,
    a second request to another site that weeds out honeypots, and a known page that has to arrive unchanged.
    "Passed every check" is the number of proxies from a source that got through all of that in an average recent
    run, "Share" is that number against the proxies checked from it.</p>
    <p>A proxy that several lists carry counts for each of them. The files of one repository are one source.
    A run checks the most promising 150,000 candidates, so of a very large list only a part is checked each time.
    The lists published by proxy-scraper itself are left out: they are the result of these checks.</p>
    <p>The same ranking from your own network: <code class="mono">proxy-scraper --list-sources</code>.
    A list is missing? <a href="{REPO_URL}/issues/new?template=new_source.yml">Add it as a source</a>.</p>
  </section>
  <footer>
    <span>Free proxies are run by strangers. Never send passwords or personal data through them.</span>
    <span>Collected and checked by <a href="{REPO_URL}">proxy-scraper</a>, open source, MIT licensed.</span>
  </footer>
</div>
</body>
</html>
"""


def write_source_pages(quality: Optional[SourceStats], out: Path, updated: datetime) -> List[str]:
    """Writes sources/index.html and sources.json -> the paths for the sitemap (none without statistics)."""
    ranking = rank(quality, updated) if quality is not None else []
    if not ranking:
        return []
    folder = out / "sources"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "index.html").write_text(page(ranking, updated), encoding="utf-8")
    (out / "sources.json").write_text(json.dumps(
        {"updated": updated.isoformat(timespec="seconds"), "sources": ranking}, indent=1, ensure_ascii=False),
        encoding="utf-8")
    return ["sources/"]
