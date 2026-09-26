"""Static pages for search engines: one per protocol, per filter and per country, plus a sitemap.

The website itself loads everything with JavaScript, so a search engine mostly sees an empty shell. These
pages carry the proxies as plain HTML: "free socks5 proxy list" or "free proxies germany" land on a page
that answers exactly that, and every page links back to the full, filterable list.
"""

from __future__ import annotations

from datetime import datetime
from html import escape
from pathlib import Path
from typing import Callable, Dict, List, Tuple

SITE_URL = "https://maximilianfeix.github.io/proxy-scraper/"
REPO_URL = "https://github.com/maximilianfeix/proxy-scraper"
ROWS_PER_PAGE = 200
SITEMAP_MIN = 3  # countries with fewer proxies still get their page, but aren't advertised in the sitemap

# every country here always gets a page, so its URL never disappears between runs (empty ones say so)
COUNTRIES = {
    "AE": "the United Arab Emirates", "AR": "Argentina", "AT": "Austria", "AU": "Australia", "BD": "Bangladesh",
    "BE": "Belgium", "BG": "Bulgaria", "BR": "Brazil", "CA": "Canada", "CH": "Switzerland", "CL": "Chile",
    "CN": "China", "CO": "Colombia", "CZ": "Czechia", "DE": "Germany", "DK": "Denmark", "EC": "Ecuador",
    "EE": "Estonia", "EG": "Egypt", "ES": "Spain", "FI": "Finland", "FR": "France", "GB": "the United Kingdom",
    "GR": "Greece", "HK": "Hong Kong", "HR": "Croatia", "HU": "Hungary", "ID": "Indonesia", "IE": "Ireland",
    "IL": "Israel", "IN": "India", "IQ": "Iraq", "IR": "Iran", "IT": "Italy", "JP": "Japan", "KE": "Kenya",
    "KH": "Cambodia", "KR": "South Korea", "KZ": "Kazakhstan", "LT": "Lithuania", "LV": "Latvia", "MA": "Morocco",
    "MX": "Mexico", "MY": "Malaysia", "NG": "Nigeria", "NL": "the Netherlands", "NO": "Norway", "NP": "Nepal",
    "NZ": "New Zealand", "PE": "Peru", "PH": "the Philippines", "PK": "Pakistan", "PL": "Poland", "PT": "Portugal",
    "RO": "Romania", "RS": "Serbia", "RU": "Russia", "SA": "Saudi Arabia", "SE": "Sweden", "SG": "Singapore",
    "TH": "Thailand", "TR": "Turkey", "TW": "Taiwan", "UA": "Ukraine", "US": "the United States",
    "VE": "Venezuela", "VN": "Vietnam", "ZA": "South Africa",
}

Filter = Callable[[dict], bool]


def _short_name(country: str) -> str:
    return country[4:] if country.startswith("the ") else country


def page_specs() -> List[Tuple[str, str, str, Filter]]:
    """(path, title, what one proxy is called in the lede, filter) for every page."""
    specs: List[Tuple[str, str, str, Filter]] = [
        ("http/", "Free HTTP proxy list", "HTTP proxies", lambda r: r["ptype"] == "http"),
        ("socks4/", "Free SOCKS4 proxy list", "SOCKS4 proxies", lambda r: r["ptype"] == "socks4"),
        ("socks5/", "Free SOCKS5 proxy list", "SOCKS5 proxies", lambda r: r["ptype"] == "socks5"),
        ("https/", "Free HTTPS proxy list", "proxies that tunnel HTTPS with verified TLS",
         lambda r: bool(r.get("https"))),
        ("elite/", "Free elite proxy list", "elite proxies (no forwarded IP, no Via header)",
         lambda r: r.get("anonymity") == "elite"),
    ]
    for cc, name in sorted(COUNTRIES.items(), key=lambda kv: _short_name(kv[1])):
        specs.append((f"country/{cc.lower()}/", f"Free proxies in {_short_name(name)}",
                      f"proxies in {name}", lambda r, cc=cc: r.get("country") == cc))
    return specs


CSS = """
:root { --bg: #121113; --panel: #1A191C; --line: #2B292F; --text: #EDEBE6; --muted: #9A97A0; --signal: #D4F77A;
        --signal-ink: #D4F77A; --on-signal: #121113; color-scheme: dark; }
@media (prefers-color-scheme: light) {
  :root { --bg: #EFEFEC; --panel: #FFFFFF; --line: #DAD9D4; --text: #121113; --muted: #5F5C66;
          --signal-ink: #3F5A00; color-scheme: light; }
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--text); font: 400 16px/1.55 "Geist", ui-sans-serif, system-ui,
       sans-serif; padding-inline: 16px; }
.wrap { max-width: 1080px; margin: 0 auto; padding-block: 28px 64px; display: grid; gap: 36px; }
a { color: var(--signal-ink); }
:focus-visible { outline: 2px solid var(--signal-ink); outline-offset: 3px; border-radius: 6px; }
.mono { font-family: "Geist Mono", ui-monospace, Menlo, monospace; }
header { display: flex; justify-content: space-between; align-items: center; gap: 16px; flex-wrap: wrap; }
.brand { display: flex; align-items: center; gap: 10px; color: var(--text); text-decoration: none; font-weight: 600;
         letter-spacing: -.03em; font-size: 18px; }
.brand img { width: 30px; height: 30px; border-radius: 9px; }
h1 { margin: 0; font-size: clamp(36px, 6vw, 72px); line-height: 1; letter-spacing: -.05em; font-weight: 600;
     text-wrap: balance; }
.lede { margin: 16px 0 0; color: var(--muted); font-size: 18px; max-width: 62ch; }
.actions { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 22px; }
.btn { display: inline-flex; align-items: center; padding: 10px 18px; border-radius: 99px; text-decoration: none;
       font-weight: 500; border: 1px solid var(--line); color: var(--text); }
.btn.primary { background: var(--signal); color: var(--on-signal); border-color: var(--signal); }
.table { overflow-x: auto; background: var(--panel); border: 1px solid var(--line); border-radius: 16px; }
table { border-collapse: collapse; width: 100%; min-width: 640px; font-size: 14px; }
caption { text-align: left; padding: 14px 16px 0; color: var(--muted); font-size: 13px; }
th { text-align: left; font-weight: 500; color: var(--muted); padding: 12px 16px;
     border-bottom: 1px solid var(--line); }
td { padding: 10px 16px; border-bottom: 1px solid var(--line); font-variant-numeric: tabular-nums;
     white-space: nowrap; }
tr:last-child td { border-bottom: 0; }
.empty { padding: 28px 16px; color: var(--muted); }
nav h2 { font-size: 15px; font-weight: 500; color: var(--muted); margin: 0 0 10px; }
nav ul { list-style: none; margin: 0; padding: 0; display: flex; flex-wrap: wrap; gap: 8px; }
nav a { display: inline-block; padding: 5px 12px; border: 1px solid var(--line); border-radius: 99px;
        text-decoration: none; color: var(--text); font-size: 14px; }
nav a[aria-current] { background: var(--signal); color: var(--on-signal); border-color: var(--signal); }
footer { color: var(--muted); font-size: 14px; display: grid; gap: 6px; }
"""


def _render(path: str, title: str, what: str, rows: List[dict], updated: datetime, nav: str) -> str:
    depth = path.count("/")
    root = "../" * depth
    total = len(rows)
    when = updated.strftime("%d %b %Y, %H:%M UTC")
    if total:
        lede = (f"{total:,} {what} that worked in the last check ({when}). Each one passed a real handshake, "
                "a honeypot check on two sites and a content check, so none of them rewrite the pages you load.")
    else:
        lede = (f"No {what} passed every check in the last run ({when}). The list is checked again every hour, "
                "so look again later or try the full list.")
    body_rows = "\n".join(
        f"<tr><td class=\"mono\">{escape(r['proxy'])}</td><td>{escape(r['ptype'].upper())}</td>"
        f"<td>{escape(r.get('country') or '–')}</td><td>{r['latency']:,} ms</td>"
        f"<td>{'yes' if r.get('https') else 'no'}</td><td>{escape(r.get('anonymity') or '–')}</td>"
        f"<td>{escape((r.get('org') or '–')[:40])}</td></tr>"
        for r in rows[:ROWS_PER_PAGE])
    table = (f"<div class=\"table\"><table><caption>The {min(total, ROWS_PER_PAGE):,} fastest, as ip:port. "
             f"The download has all {total:,} as type://ip:port.</caption>"
             "<thead><tr><th scope=\"col\">Proxy</th><th scope=\"col\">Type</th><th scope=\"col\">Country</th>"
             "<th scope=\"col\">Latency</th><th scope=\"col\">HTTPS</th><th scope=\"col\">Anonymity</th>"
             f"<th scope=\"col\">Provider</th></tr></thead><tbody>{body_rows}</tbody></table></div>"
             if total else "")
    description = (f"{total:,} free {what}, checked every hour: real handshake, honeypot and content check. "
                   "Download as text or filter the full list.")
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)} – checked every hour | proxy-scraper</title>
<meta name="description" content="{escape(description)}">
<link rel="canonical" href="{SITE_URL}{path}">
<meta property="og:title" content="{escape(title)}">
<meta property="og:description" content="{escape(description)}">
<meta property="og:image" content="{SITE_URL}og.png">
<meta property="og:url" content="{SITE_URL}{path}">
<meta name="twitter:card" content="summary_large_image">
<link rel="icon" href="{root}logo.png">
<link rel="apple-touch-icon" href="{root}apple-touch-icon.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Geist:wght@400..700&family=Geist+Mono:wght@400;500&display=swap"
      rel="stylesheet">
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
  <header>
    <a class="brand" href="{root}"><img src="{root}logo.png" alt="">proxy-scraper</a>
    <a href="{root}">All proxies</a>
  </header>
  <main>
    <h1>{escape(title)}</h1>
    <p class="lede">{escape(lede)}</p>
    <div class="actions">
      <a class="btn primary" href="proxies.txt" download>Download {total:,} as .txt</a>
      <a class="btn" href="{root}#list">Filter the full list</a>
      <a class="btn" href="{REPO_URL}">Check them from your network</a>
    </div>
  </main>
  {table}
  {nav}
  <footer>
    <span>Free proxies are run by strangers. Never send passwords or personal data through them.</span>
    <span>Collected and checked by <a href="{REPO_URL}">proxy-scraper</a>, open source, MIT licensed.</span>
  </footer>
</div>
</body>
</html>
"""


def _nav(specs, counts: Dict[str, int], current: str, root: str) -> str:
    def links(items):
        here = ' aria-current="page"'
        return "".join(f'<li><a href="{root}{p}"{here if p == current else ""}>{escape(label)} ({counts[p]:,})</a></li>'
                       for p, label in items)

    kinds = [(p, t.replace("Free ", "").replace(" proxy list", ""))
             for p, t, _, _ in specs if not p.startswith("country/")]
    countries = sorted(((p, t.replace("Free proxies in ", "")) for p, t, _, _ in specs
                        if p.startswith("country/") and counts[p]), key=lambda pt: -counts[pt[0]])
    return (f"<nav aria-label=\"More lists\"><h2>By protocol</h2><ul>{links(kinds)}</ul></nav>"
            f"<nav aria-label=\"By country\"><h2>By country</h2><ul>{links(countries)}</ul></nav>")


def write_pages(rows: List[dict], out: Path, updated: datetime) -> List[str]:
    """Writes every page with its proxies.txt and the sitemap. -> the paths listed in the sitemap."""
    rows = sorted(rows, key=lambda r: r["latency"])
    specs = page_specs()
    selected = {p: [r for r in rows if keep(r)] for p, _, _, keep in specs}
    counts = {p: len(v) for p, v in selected.items()}
    listed = [""]
    for path, title, what, _ in specs:
        page_rows = selected[path]
        folder = out / path
        folder.mkdir(parents=True, exist_ok=True)
        nav = _nav(specs, counts, path, "../" * path.count("/"))
        (folder / "index.html").write_text(_render(path, title, what, page_rows, updated, nav), encoding="utf-8")
        (folder / "proxies.txt").write_text("".join(f"{r['url']}\n" for r in page_rows), encoding="utf-8")
        if not path.startswith("country/") or counts[path] >= SITEMAP_MIN:
            listed.append(path)
    lastmod = updated.strftime("%Y-%m-%dT%H:%M:%S+00:00")
    urls = "".join(f"<url><loc>{SITE_URL}{p}</loc><lastmod>{lastmod}</lastmod><changefreq>hourly</changefreq></url>"
                   for p in listed)
    (out / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n'
                                     f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>\n',
                                     encoding="utf-8")
    return listed
