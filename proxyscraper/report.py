"""The weekly report: what a week of hourly checks says about free proxies – how long they last, how many
get through to the big sites, where they are. Rebuilt with every run from the same data as the list, as a page
(report/), as markdown to post elsewhere (report/report.md) and as a short post (report/post.txt).
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
from html import escape
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from .charts import FONT, THEMES, WIDTH
from .pages import COUNTRIES, CSS, SITE_URL, _short_name

DAYS = 7
RUN_HOURS = 1
REPORT_URL = f"{SITE_URL}report/"
SITE_NAMES = {"google": "Google", "reddit": "Reddit", "amazon": "Amazon"}
# how many hourly checks a proxy was on the list for -> label
BUCKETS = [(1, 1, "1 check"), (2, 5, "2–5"), (6, 23, "6–23"), (24, 71, "1–3 days"), (72, 10 ** 6, "3 days +")]


def _when(run: dict) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(run["updated"])
    except (KeyError, TypeError, ValueError):
        return None


def _pct(part: int, whole: int) -> int:
    return round(100 * part / whole) if whole else 0


def weekly_facts(rows: List[dict], runs: Sequence[dict], seen: Dict[str, int], now: datetime) -> dict:
    """rows: this run's list, runs: history.json (oldest first, this run last), seen: url -> bits (bit 0 = this
    run) from seen.json."""
    since_limit = now - timedelta(days=DAYS)
    window = [(t, r) for r in runs if (t := _when(r)) and t > since_limit]
    mask = (1 << len(window)) - 1
    # how many of the window's checks each proxy passed – not the ones that showed up for the first time just now:
    # nobody knows yet how long they'll last
    listed = [n for bits in seen.values() if (n := bin(bits & mask).count("1")) and not (n == 1 and bits & 1)]
    day = 24 // RUN_HOURS
    totals = [r.get("total", 0) for _, r in window]

    sites = {}
    for key in SITE_NAMES:
        answered = [r for r in rows if key in (r.get("sites") or {})]
        dc = [r for r in answered if r.get("hosting")]
        other = [r for r in answered if r.get("hosting") is False]
        sites[key] = {"through": sum(1 for r in answered if r["sites"][key]), "answered": len(answered),
                      "datacenter": _pct(sum(1 for r in dc if r["sites"][key]), len(dc)),
                      "other": _pct(sum(1 for r in other if r["sites"][key]), len(other))}

    return {
        "now": now, "since": window[0][0] if window else now, "runs": len(window),
        "distinct": len(listed),
        "gone_after_one_run": sum(1 for n in listed if n == 1),
        "lasted_a_day": sum(1 for n in listed if n >= day),
        "lasted_whole_window": sum(1 for n in listed if n == len(window)) if len(window) > 1 else 0,
        "lifetimes": [(label, sum(1 for n in listed if lo <= n <= hi)) for lo, hi, label in BUCKETS],
        "peak": max(totals, default=len(rows)), "low": min(totals, default=len(rows)),
        "total": len(rows),
        "by_type": dict(Counter(r["ptype"] for r in rows)),
        "https": _pct(sum(1 for r in rows if r.get("https")), len(rows)),
        "datacenter": _pct(sum(1 for r in rows if r.get("hosting")), len(rows)),
        "countries": Counter(r["country"] for r in rows if r.get("country")).most_common(5),
        "latency_now": window[-1][1].get("median_latency") if window else None,
        "sites": sites,
    }


def _country(cc: str) -> str:
    return _short_name(COUNTRIES[cc]) if cc in COUNTRIES else cc


def _period(f: dict) -> str:
    return f"{f['since']:%b %d} – {f['now']:%b %d, %Y}"


def _lines(f: dict) -> List[str]:
    """The findings as sentences, most striking first – shared by the page, the markdown and the post."""
    out = []
    if f["distinct"]:
        out.append(f"{f['distinct']:,} different proxies passed every check at least once. "
                   f"{_pct(f['gone_after_one_run'], f['distinct'])} % of them were gone by the next hourly check, "
                   f"and only {f['lasted_a_day']:,} ({_pct(f['lasted_a_day'], f['distinct'])} %) were on the list "
                   "for a day's worth of checks or more.")
    for key, s in f["sites"].items():
        if s["answered"]:
            line = f"{SITE_NAMES[key]} let {_pct(s['through'], s['answered'])} % through"
            if s["datacenter"] or s["other"]:
                line += f" – {s['datacenter']} % of datacenter exits, {s['other']} % of the rest"
            out.append(line + ".")
    out.append(f"Between {f['low']:,} and {f['peak']:,} proxies worked at any one time. Right now: {f['total']:,}, "
               f"{f['https']} % of them tunnel HTTPS, {f['datacenter']} % exit from a datacenter.")
    if f["countries"]:
        out.append("Most of them sit in " + ", ".join(f"{_country(cc)} ({n:,})" for cc, n in f["countries"]) + ".")
    return out


def markdown(f: dict) -> str:
    lines = "\n\n".join(_lines(f))
    return f"""# The week in free proxies: {_period(f)}

Every hour, [proxy-scraper](https://github.com/maximilianfeix/proxy-scraper) collects public HTTP, SOCKS4 and SOCKS5
proxies from 700+ lists and keeps only the ones that pass a real handshake, a honeypot check and a content check.
This is what {f['runs']:,} of those hourly runs looked like.

{lines}

![How long free proxies last]({REPORT_URL}lifetimes-light.svg)

The list, filters and a page per proxy: {SITE_URL}
Raw data (JSON, CSV, TXT): {SITE_URL}proxies.json

*Generated automatically from the hourly checks. Public proxies are run by strangers – never send passwords or
personal data through them.*
"""


def post(f: dict) -> str:
    """A post that fits on X (280 characters)."""
    if f["distinct"]:
        text = (f"{f['distinct']:,} free proxies worked at some point this week. "
                f"{_pct(f['gone_after_one_run'], f['distinct'])} % were gone an hour later, "
                f"{_pct(f['lasted_a_day'], f['distinct'])} % lasted a day.")
        amazon = f["sites"].get("amazon", {})
        if amazon.get("answered"):
            text += f" Amazon let {_pct(amazon['through'], amazon['answered'])} % through."
    else:
        text = f"{f['total']:,} free proxies passed every check this hour."
    link = REPORT_URL.replace("https://", "")
    return f"{text}\n\nThe week in numbers: {link}"[:280]


def lifetimes_svg(f: dict, theme: str) -> str:
    c = THEMES[theme]
    buckets = f["lifetimes"]
    most = max((n for _, n in buckets), default=0) or 1
    total = sum(n for _, n in buckets) or 1
    height, row = 64 + 34 * len(buckets), 34
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{height}" '
             f'viewBox="0 0 {WIDTH} {height}" font-family="{FONT}" role="img" '
             f'aria-label="How many hourly checks free proxies lasted">',
             f'<rect width="{WIDTH}" height="{height}" rx="16" fill="{c["bg"]}"/>',
             f'<text x="28" y="38" fill="{c["muted"]}" font-size="14">On the list for …</text>']
    for i, (label, n) in enumerate(buckets):
        y = 58 + i * row
        width = (WIDTH - 200 - 150) * n / most
        parts += [f'<text x="28" y="{y + 13}" fill="{c["text"]}" font-size="14">{escape(label)}</text>',
                  f'<rect x="200" y="{y}" width="{max(width, 2):.1f}" height="18" rx="4" fill="{c["socks5"]}"/>',
                  f'<text x="{210 + width:.1f}" y="{y + 13}" fill="{c["muted"]}" font-size="13">'
                  f'{n:,} ({_pct(n, total)} %)</text>']
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def page(f: dict) -> str:
    items = "".join(f"<p>{escape(line)}</p>" for line in _lines(f))
    root = "../"
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>The week in free proxies ({escape(_period(f))}) | proxy-scraper</title>
<meta name="description" content="{escape(_lines(f)[0])}">
<link rel="canonical" href="{REPORT_URL}">
<meta property="og:title" content="The week in free proxies">
<meta property="og:description" content="{escape(_lines(f)[0])}">
<meta property="og:image" content="{SITE_URL}og.png">
<link rel="icon" href="{root}logo.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Geist:wght@400..700&family=Geist+Mono:wght@400;500&display=swap"
      rel="stylesheet">
<style>{CSS}
.report p {{ font-size: 19px; max-width: 64ch; margin: 0 0 18px; }}
.report p:first-child {{ font-size: 24px; letter-spacing: -.01em; }}
picture img {{ width: 100%; height: auto; border-radius: 16px; }}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <a class="brand" href="{root}"><img src="{root}logo.png" alt="">proxy-scraper</a>
    <a href="{root}#list">The live list</a>
  </header>
  <main>
    <h1>The week in free proxies</h1>
    <p class="lede">{escape(_period(f))} · {f['runs']:,} hourly checks · updated with every run</p>
  </main>
  <section class="report">{items}</section>
  <picture>
    <source media="(prefers-color-scheme: light)" srcset="lifetimes-light.svg">
    <img src="lifetimes-dark.svg" alt="How many hourly checks free proxies lasted this week">
  </picture>
  <picture>
    <source media="(prefers-color-scheme: light)" srcset="{root}chart-light.svg">
    <img src="{root}chart-dark.svg" alt="Working proxies over the week, by protocol">
  </picture>
  <footer><span>Want to share it? <a href="report.md">Markdown</a> · <a href="post.txt">a short post</a> ·
  <a href="https://github.com/maximilianfeix/proxy-scraper">the code</a></span></footer>
</div>
</body>
</html>
"""


def write_report(f: dict, out: Path) -> None:
    folder = out / "report"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "index.html").write_text(page(f), encoding="utf-8")
    (folder / "report.md").write_text(markdown(f), encoding="utf-8")
    (folder / "post.txt").write_text(post(f) + "\n", encoding="utf-8")
    for theme in THEMES:
        (folder / f"lifetimes-{theme}.svg").write_text(lifetimes_svg(f, theme), encoding="utf-8")
