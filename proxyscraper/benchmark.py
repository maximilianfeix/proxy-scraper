"""Which free proxy list on GitHub actually works? The popular lists side by side, rewritten with every run.

The numbers are the ones of the source ranking (sourcepages.rank): per list, how many of its proxies were checked
in an average recent run and how many of those passed every check. This page only picks the well-known GitHub
lists out of it, orders them by that share and adds a chart that can be shared or embedded.
"""

from __future__ import annotations

import json
import statistics
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Dict, List, Optional
from xml.sax.saxutils import escape as xml_escape

from .charts import FONT, THEMES, WIDTH
from .pages import CSS, PAGE_CSS, REPO_URL, SITE_URL

# The free proxy lists people find first on GitHub. Only the ones present in the statistics are shown; a repository
# that is renamed or dropped simply disappears from the page until it is changed here.
POPULAR = (
    "proxifly/free-proxy-list", "TheSpeedX/PROXY-List", "monosans/proxy-list", "jetkai/proxy-list",
    "clarketm/proxy-list", "ProxyScrape/free-proxy-list", "roosterkid/openproxylist", "mmpx12/proxy-list",
    "hookzof/socks5_list", "vakhov/fresh-proxy-list", "ErcinDedeoglu/proxies", "r00tee/Proxy-List",
    "Zaeem20/FREE_PROXIES_LIST", "iplocate/free-proxy-list", "sunny9577/proxy-scraper", "zloi-user/hideip.me",
)
MIN_CHECKED = 300  # below this many checks per run a share says too little: such a list is shown, but not ranked

STATUS = {"outdated": "unchanged for a week", "unreachable": "doesn't load", "dead": "nothing passes"}


def select(ranking: List[dict]) -> List[dict]:
    """The popular lists out of the ranking of all sources, highest share first. Each gets "rank": its place, or
    None when too few of its proxies were checked to compare it (those go last)."""
    wanted = {name.lower(): name for name in POPULAR}
    # GitHub names ignore case, the sources don't: the same repository can come in under two spellings. The same
    # files fetched twice carry the same proxies, so keep the entry with the most checks (not the sum), named as here.
    best: Dict[str, dict] = {}
    for s in ranking:
        key = s["name"].lower()
        if key in wanted and s.get("checked") and (key not in best or s["checked"] > best[key]["checked"]):
            best[key] = dict(s, name=wanted[key])
    picked = list(best.values())
    ranked = sorted((s for s in picked if s["checked"] >= MIN_CHECKED),
                    key=lambda s: (-s["share"], -s["working"], s["name"].lower()))
    rest = sorted((s for s in picked if s["checked"] < MIN_CHECKED), key=lambda s: s["name"].lower())
    for i, s in enumerate(ranked, 1):
        s["rank"] = i
    for s in rest:
        s["rank"] = None
    return ranked + rest


def _when(stamp: Optional[str]) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(stamp) if stamp else None
    except (TypeError, ValueError):
        return None


def ago(stamp: Optional[str], now: datetime) -> str:
    """When a list last changed, the way a person says it: "2 h ago", "3 days ago", "27 Sep 2026"."""
    then = _when(stamp)
    if then is None:
        return "–"
    hours = (now - then).total_seconds() / 3600
    if hours < 1:
        return "within the hour"
    if hours < 48:
        return f"{int(hours)} h ago"
    if hours < 14 * 24:
        return f"{int(hours // 24)} days ago"
    return then.strftime("%d %b %Y").lstrip("0")


CHART_ROW = 30


def chart_svg(lists: List[dict], updated: datetime, theme: str = "dark") -> str:
    """The ranked lists as horizontal bars of their share – plain SVG like the README charts, to share or embed."""
    c = THEMES[theme]
    ranked = [s for s in lists if s.get("rank")]
    top, left, bar_left, bar_right = 112, 28, 300, WIDTH - 90
    height = top + CHART_ROW * max(len(ranked), 1) + 52
    most = max((s["share"] for s in ranked), default=0.0) or 1.0
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{height}" '
             f'viewBox="0 0 {WIDTH} {height}" font-family="{FONT}" role="img" '
             'aria-label="Share of checked proxies that passed every check, per popular free proxy list on GitHub">',
             f'<rect width="{WIDTH}" height="{height}" rx="16" fill="{c["bg"]}"/>',
             f'<text x="{left}" y="52" fill="{c["text"]}" font-size="22" font-weight="600" letter-spacing="-0.4">'
             'Which free proxy list on GitHub actually works?</text>',
             f'<text x="{left}" y="80" fill="{c["muted"]}" font-size="14">Share of checked proxies that passed every '
             f'check, average of recent hourly runs · {xml_escape(updated.strftime("%d %b %Y"))}</text>']
    for i, s in enumerate(ranked):
        y = top + i * CHART_ROW
        width = (bar_right - bar_left) * s["share"] / most
        parts += [f'<text x="{left}" y="{y + 13}" fill="{c["text"]}" font-size="14">{xml_escape(s["name"])}</text>',
                  f'<rect x="{bar_left}" y="{y}" width="{bar_right - bar_left}" height="16" rx="3" '
                  f'fill="{c["panel"]}"/>',
                  f'<rect x="{bar_left}" y="{y}" width="{max(width, 2):.1f}" height="16" rx="3" fill="{c["socks5"]}"/>',
                  f'<text x="{bar_right + 12}" y="{y + 13}" fill="{c["text"]}" font-size="14" '
                  f'font-variant-numeric="tabular-nums">{s["share"]:.1f} %</text>']
    if not ranked:
        parts.append(f'<text x="{left}" y="{top + 13}" fill="{c["muted"]}" font-size="14">'
                     'Not enough checks yet – the chart fills up with the next runs</text>')
    parts.append(f'<text x="{left}" y="{height - 24}" fill="{c["muted"]}" font-size="12">Checked about every hour '
                 'from a GitHub Actions runner by proxy-scraper · proxy-scraper.de/benchmark/</text>')
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


BENCH_CSS = """
td.num, th.num { text-align: right; }
td .muted { color: var(--muted); }
.share-cell { display: inline-flex; align-items: center; gap: 10px; }
.bar { width: 96px; height: 6px; border-radius: 3px; background: var(--line); overflow: hidden; flex: none; }
.bar i { display: block; height: 100%; background: var(--signal-ink); border-radius: 3px; }
.method p, .method li { color: var(--muted); max-width: 70ch; }
.method p { margin: 0 0 12px; }
.method ul { margin: 0 0 12px; padding-left: 20px; }
.method li { margin-bottom: 6px; }
.method strong { color: var(--text); font-weight: 500; }
.share-it pre { background: var(--panel); border: 1px solid var(--line); border-radius: 12px; padding: 14px 16px;
                overflow-x: auto; font-size: 13px; margin: 0 0 10px; }
"""


def _table(lists: List[dict], now: datetime) -> str:
    most = max((s["share"] for s in lists if s.get("rank")), default=0.0) or 1.0

    def row(s: dict) -> str:
        note = STATUS.get(s.get("status", ""), "")
        stamp = escape(s["last_change"] or "", quote=True)
        changed = (f'<time datetime="{stamp}">{escape(ago(s["last_change"], now))}</time>' if s.get("last_change")
                   else "–") + (f' <span class="muted">· {note}</span>' if note else "")
        listed = "–" if s.get("status") == "unreachable" else f'{s["listed"]:,}'
        place = s["rank"] if s.get("rank") else '<span class="muted" title="too few checked to compare">–</span>'
        bar = (f'<span class="bar" aria-hidden="true"><i style="width:{100 * s["share"] / most:.0f}%"></i></span>'
               if s.get("rank") else "")
        return (f'<tr><td class="num">{place}</td><td><a href="{escape(s["url"], quote=True)}" '
                f'rel="nofollow noopener">{escape(s["name"])}</a></td><td class="num">{listed}</td>'
                f'<td class="num">{s["checked"]:,}</td><td class="num">{s["working"]:,}</td>'
                f'<td class="num"><span class="share-cell">{bar}<span>{s["share"]:.1f}&nbsp;%</span></span></td>'
                f'<td>{changed}</td></tr>')

    rows = "\n".join(row(s) for s in lists)
    return ('<div class="table" tabindex="0" role="region" aria-label="The popular lists compared">'
            '<table><caption>Per list, in an average recent run: proxies in the latest download, '
            'how many of them were checked, how many passed every check and their share. Highest share first.'
            '</caption><thead><tr><th scope="col" class="num">#</th><th scope="col">List</th>'
            '<th scope="col" class="num">Proxies listed</th><th scope="col" class="num">Checked</th>'
            '<th scope="col" class="num">Passed every check</th><th scope="col" class="num">Share</th>'
            f'<th scope="col">Last change</th></tr></thead><tbody>{rows}</tbody></table></div>')


def page(lists: List[dict], updated: datetime) -> str:
    root = "../"
    when = updated.strftime("%d %b %Y, %H:%M UTC")
    ranked = [s for s in lists if s.get("rank")]
    title = "Which free proxy list on GitHub actually works?"
    if ranked:
        best = ranked[0]
        typical = statistics.median(s["share"] for s in ranked)
        lede = (f"{len(lists)} popular free proxy lists on GitHub, checked about every hour. In recent runs "
                f"{best['name']} had the highest share of its checked proxies pass every check, "
                f"{best['share']:.1f}\u00a0%; "
                f"in the typical list it was {typical:.1f}\u00a0%. Updated {when}.")
        facts = (f'<div><dt>{len(lists)}</dt><dd>popular lists compared</dd></div>'
                 f'<div><dt>{best["share"]:.1f} %</dt><dd>highest share ({escape(best["name"])})</dd></div>'
                 f'<div><dt>{typical:.1f} %</dt><dd>in the typical list (median)</dd></div>'
                 f'<div><dt>{sum(s["checked"] for s in lists):,}</dt>'
                 '<dd>proxies checked per run, counted per list</dd></div>')
    else:
        typical = 0.0
        lede = ("Popular free proxy lists on GitHub, checked about every hour. Too few of their proxies have been "
                f"checked yet to compare them; the table fills up with the next runs. Updated {when}.")
        facts = f'<div><dt>{len(lists)}</dt><dd>popular lists compared</dd></div>' if lists else ""
    description = ("Popular free proxy lists on GitHub, checked every hour: the share of their proxies "
                   "that pass a handshake, a second request and an unchanged test page"
                   + (f" ranges from {ranked[-1]['share']:.1f} % to {ranked[0]['share']:.1f} %." if ranked else "."))
    dataset = json.dumps({
        "@context": "https://schema.org", "@type": "Dataset", "name": title, "description": description,
        "url": f"{SITE_URL}benchmark/", "dateModified": updated.isoformat(timespec="seconds"),
        "creator": {"@type": "Organization", "name": "proxy-scraper", "url": REPO_URL},
        "license": "https://opensource.org/licenses/MIT", "isAccessibleForFree": True,
        "distribution": [{"@type": "DataDownload", "encodingFormat": "application/json",
                          "contentUrl": f"{SITE_URL}benchmark.json"}],
    }, ensure_ascii=False).replace("</", "<\\/")
    embed = (f'<a href="{SITE_URL}benchmark/"><picture>\n'
             f'  <source media="(prefers-color-scheme: light)" srcset="{SITE_URL}benchmark-light.svg">\n'
             f'  <img src="{SITE_URL}benchmark-dark.svg" alt="Which free proxy list on GitHub actually works?" '
             'width="100%">\n</picture></a>')
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} Free proxy lists compared every hour | proxy-scraper</title>
<meta name="description" content="{escape(description)}">
<link rel="canonical" href="{SITE_URL}benchmark/">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{escape(description)}">
<meta property="og:image" content="{SITE_URL}og.png">
<meta property="og:url" content="{SITE_URL}benchmark/">
<meta name="twitter:card" content="summary_large_image">
<link rel="icon" href="{root}logo.png">
<link rel="apple-touch-icon" href="{root}apple-touch-icon.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Geist:wght@400..700&family=Geist+Mono:wght@400;500&display=swap"
      rel="stylesheet">
<style>{CSS}{PAGE_CSS}{BENCH_CSS}</style>
<script type="application/ld+json">{dataset}</script>
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
      <a class="btn" href="{root}sources/">All sources ranked</a>
      <a class="btn" href="{root}benchmark.json">As JSON</a>
    </div>
  </main>
  <dl class="facts">{facts}</dl>
  <section><h2>The popular lists, side by side</h2>
  {_table(lists, updated)}
  </section>
  <section class="method"><h2>How it's measured</h2>
    <p>About every hour a GitHub Actions runner downloads each of these lists and checks its proxies.
    A proxy <strong>passed every check</strong> when it got through all three:</p>
    <ul>
      <li>a real HTTP, SOCKS4 or SOCKS5 handshake that returns a foreign exit IP,</li>
      <li>a second request to another site that has to show the same exit IP,</li>
      <li>a static test page that has to arrive unchanged, byte for byte.</li>
    </ul>
    <p><strong>Share</strong> is the proxies that passed against the proxies checked from that list. Both are averages
    of recent runs in which every run counts twice as much as the one before it, so the latest run makes up about half
    and the last few hours almost all of it. <strong>Proxies listed</strong> is the latest successful download, which
    is why <em>checked</em> can come out a little above it.</p>
    <p>One run checks only the most promising part of the candidates from all the lists it knows, so of a big list
    only a part is checked each time. That part is not a random sample: proxies that worked before go first. A proxy
    that several lists carry counts for each of them, and all files of one repository count as one list. Lists with
    fewer than {MIN_CHECKED:,} proxies checked per run are shown without a place.</p>
    <p>This is one measurement from one data center network, not a judgment of the maintainers. Many of these lists
    publish what they collect without filtering it, refresh at different times or are meant for other uses; a low share
    mostly means that many entries were offline or didn't pass at the moment they were checked. From your own network
    the numbers can differ.</p>
    <p>proxy-scraper's own published list is not in the table. It is made of the proxies that passed these same checks
    an hour earlier, so measuring it with them would not be a fair comparison.</p>
    <p>Every list it knows, not only these, is ranked on <a href="{root}sources/">the sources page</a>. The same
    numbers from your own network: <code class="mono">proxy-scraper --list-sources</code>.</p>
  </section>
  <section class="share-it"><h2>Share or embed the chart</h2>
    <p class="note">Rewritten with every run: <a href="{root}benchmark-light.svg">light</a> ·
    <a href="{root}benchmark-dark.svg">dark</a>. For a README:</p>
    <pre class="mono">{escape(embed)}</pre>
  </section>
  <footer>
    <span>Free proxies are run by strangers. Never send passwords or personal data through them.</span>
    <span>Collected and checked by <a href="{REPO_URL}">proxy-scraper</a>, open source, MIT licensed.</span>
  </footer>
</div>
</body>
</html>
"""


def write_benchmark(ranking: List[dict], out: Path, updated: datetime) -> List[str]:
    """Writes benchmark/index.html, benchmark.json and the chart in both themes -> the paths for the sitemap
    (always, so the links to it never point at nothing; without checked lists the page says so)."""
    lists = select(ranking)
    folder = out / "benchmark"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "index.html").write_text(page(lists, updated), encoding="utf-8")
    fields = ("rank", "name", "url", "lists", "listed", "checked", "working", "share", "last_change", "status")
    (out / "benchmark.json").write_text(json.dumps({
        "updated": updated.astimezone(timezone.utc).isoformat(timespec="seconds"),
        "measured": "average recent run (decaying, every run counts twice as much as the one before), "
                    "from a GitHub Actions runner",
        "passed_every_check": ["handshake with a foreign exit IP", "second request with the same exit IP",
                               "unchanged test page"],
        "min_checked_to_rank": MIN_CHECKED,
        "lists": [{k: s.get(k) for k in fields} for s in lists],
        "not_measured": [n for n in POPULAR if n.lower() not in {s["name"].lower() for s in lists}],
    }, indent=1, ensure_ascii=False), encoding="utf-8")
    for theme in THEMES:
        (out / f"benchmark-{theme}.svg").write_text(chart_svg(lists, updated, theme), encoding="utf-8")
    return ["benchmark/"]
