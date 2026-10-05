"""Static pages for search engines: one per protocol, per filter and per country, plus a sitemap.

The website itself loads everything with JavaScript, so a search engine mostly sees an empty shell. These
pages carry the proxies as plain HTML: "free socks5 proxy list" or "free proxies germany" land on a page
that answers exactly that, and every page links back to the full, filterable list.
"""

from __future__ import annotations

import json
import statistics
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Callable, Dict, List, Sequence, Tuple

from .ranking import best_first

SITE_URL = "https://maximilianfeix.github.io/proxy-scraper/"
REPO_URL = "https://github.com/maximilianfeix/proxy-scraper"
ROWS_PER_PAGE = 200
SITEMAP_MIN = 3  # countries with fewer proxies still get their page, but aren't advertised in the sitemap

# every country here always gets a page, so its URL never disappears between runs (empty ones say so)
COUNTRIES = {
    "AE": "the United Arab Emirates", "AL": "Albania", "AR": "Argentina", "AT": "Austria", "AU": "Australia",
    "AZ": "Azerbaijan", "BD": "Bangladesh", "BE": "Belgium", "BF": "Burkina Faso", "BG": "Bulgaria",
    "BI": "Burundi", "BM": "Bermuda", "BR": "Brazil", "CA": "Canada", "CH": "Switzerland", "CL": "Chile",
    "CN": "China", "CO": "Colombia", "CY": "Cyprus", "CZ": "Czechia", "DE": "Germany", "DK": "Denmark",
    "EC": "Ecuador", "EE": "Estonia", "EG": "Egypt", "ES": "Spain", "FI": "Finland", "FR": "France",
    "GB": "the United Kingdom", "GH": "Ghana", "GR": "Greece", "HK": "Hong Kong", "HN": "Honduras",
    "HR": "Croatia", "HU": "Hungary", "ID": "Indonesia", "IE": "Ireland", "IL": "Israel", "IN": "India",
    "IQ": "Iraq", "IR": "Iran", "IT": "Italy", "JP": "Japan", "KE": "Kenya", "KH": "Cambodia",
    "KR": "South Korea", "KZ": "Kazakhstan", "LR": "Liberia", "LT": "Lithuania", "LU": "Luxembourg",
    "LV": "Latvia", "MA": "Morocco", "MD": "Moldova", "MK": "North Macedonia", "ML": "Mali",
    "MO": "Macao", "MX": "Mexico", "MY": "Malaysia", "MZ": "Mozambique", "NE": "Niger", "NG": "Nigeria",
    "NL": "the Netherlands", "NO": "Norway", "NP": "Nepal", "NZ": "New Zealand", "PE": "Peru",
    "PH": "the Philippines", "PK": "Pakistan", "PL": "Poland", "PT": "Portugal", "PY": "Paraguay",
    "RO": "Romania", "RS": "Serbia", "RU": "Russia", "SA": "Saudi Arabia", "SC": "Seychelles",
    "SE": "Sweden", "SG": "Singapore", "SI": "Slovenia", "SK": "Slovakia", "SN": "Senegal",
    "SY": "Syria", "TH": "Thailand", "TR": "Turkey", "TW": "Taiwan", "UA": "Ukraine",
    "US": "the United States", "VE": "Venezuela", "VN": "Vietnam", "ZA": "South Africa",
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


PAGE_CSS = """
.wrap > * { min-width: 0; }  /* grid items default to their content's width: the wide table would push the page */
.facts { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 150px), 1fr)); gap: 1px; margin: 0;
         background: var(--line); border: 1px solid var(--line); border-radius: 16px; overflow: hidden; }
.facts div { background: var(--panel); padding: 16px 18px; }
.facts dt { font-size: 26px; font-weight: 600; letter-spacing: -.02em; font-variant-numeric: tabular-nums; }
.facts dd { margin: 2px 0 0; color: var(--muted); font-size: 14px; }
h2 { font-size: 24px; letter-spacing: -.02em; margin: 0 0 12px; font-weight: 600; }
.use pre { background: var(--panel); border: 1px solid var(--line); border-radius: 12px; padding: 14px 16px;
           overflow-x: auto; font-size: 14px; margin: 0 0 10px; }
.note { color: var(--muted); font-size: 14px; }
.faq h3 { font-size: 18px; font-weight: 500; margin: 22px 0 6px; }
.faq p { margin: 0; color: var(--muted); max-width: 70ch; }
"""


def _list_query(path: str) -> str:
    """The same filter on the full list: the website reads its filters from the address."""
    kind = path.strip("/")
    if kind.startswith("country/"):
        return f"?country={kind.split('/')[1].upper()}"
    return {"http": "?types=http", "socks4": "?types=socks4", "socks5": "?types=socks5", "https": "?https=1",
            "elite": "?elite=1"}.get(kind, "")


SITE_NAMES = {"tiktok": "TikTok", "discord": "Discord"}


def _pick_flags(path: str) -> str:
    """The --pick filters that give the same selection as this page."""
    kind = path.strip("/")
    if kind.startswith("country/"):
        return f"--country {kind.split('/')[1].upper()}"
    return {"http": "--types http", "socks4": "--types socks4", "socks5": "--types socks5", "https": "--https-only",
            "elite": "--anonymity elite"}.get(kind, "")


def _short(path: str) -> str:
    """How a page's proxies are called in a question: "proxies in Germany", "SOCKS5 proxies"."""
    kind = path.strip("/")
    if kind.startswith("country/"):
        return f"proxies in {_short_name(COUNTRIES.get(kind.split('/')[1].upper(), kind.split('/')[1].upper()))}"
    return {"https": "HTTPS proxies", "elite": "elite proxies"}.get(kind, f"{kind.upper()} proxies")


def _facts(rows: List[dict]) -> Dict[str, object]:
    speeds = [r["speed_kbps"] for r in rows if r.get("speed_kbps")]
    return {"total": len(rows), "https": sum(1 for r in rows if r.get("https")),
            "stable": sum(1 for r in rows if (r.get("uptime_7d") or 0) >= 90),
            # None when none of them was tried: the site check only runs on HTTPS-capable ones, and not at all
            # when it couldn't resolve the site – "0 get through" would blame proxies for a check that didn't run
            "google": (sum(1 for r in rows if (r.get("sites") or {}).get("google"))
                       if any("google" in (r.get("sites") or {}) for r in rows) else None),
            "speed": round(statistics.median(speeds)) if speeds else None}


def _faq(path: str, facts: Dict[str, object], when: str) -> List[Tuple[str, str]]:
    short, flags = _short(path), _pick_flags(path)
    if facts["google"] is None:
        got = "These proxies weren't part of the last site check – it only tries the ones that tunnel HTTPS."
    elif facts["google"]:
        got = f"In the last check, {facts['google']:,} of them got through to Google search without a captcha."
    else:
        got = "In the last check, none of them got through to Google search without a captcha."
    return [
        (f"How many free {short} work right now?",
         f"{facts['total']:,} passed every check in the last run ({when}): a real handshake, a honeypot check on two "
         f"sites and a content check. {facts['https']:,} of them tunnel HTTPS with verified TLS, and "
         f"{facts['stable']:,} were on the list in 90 % or more of this week's hourly checks. The list is checked "
         "again every hour."),
        (f"Which free {short} get through to Google?",
         f"{got} The site check also tries Reddit, Amazon, Instagram, TikTok and Discord – the full list "
         "on the website can be filtered by it."),
        (f"How do I get working {short} in code or the terminal?",
         f"Without installing anything, download proxies.txt from this page. With the tool: pipx install "
         f"proxy-scraper-cli, then proxy-scraper --pick 5 {flags} prints five from the hourly list. From Python, "
         "live_proxies() takes the same filters."),
    ]


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
    def cells(r: dict) -> str:
        through = ", ".join(SITE_NAMES.get(n, n.title()) for n, ok in (r.get("sites") or {}).items() if ok) or "–"
        return (f"<tr><td class=\"mono\"><a href=\"{root}proxy/{escape(r['proxy'].replace(':', '-'))}/\">"
                f"{escape(r['proxy'])}</a></td><td>{escape(r['ptype'].upper())}</td>"
                f"<td>{escape(r.get('country') or '–')}</td><td>{r['latency']:,} ms</td>"
                f"<td>{(str(r['speed_kbps']) + ' KB/s') if r.get('speed_kbps') else '–'}</td>"
                f"<td>{(str(r['uptime_7d']) + ' %') if r.get('uptime_7d') is not None else '–'}</td>"
                f"<td>{'yes' if r.get('https') else 'no'}</td><td>{escape(through)}</td>"
                f"<td>{escape((r.get('org') or '–')[:40])}</td></tr>")
    body_rows = "\n".join(cells(r) for r in rows[:ROWS_PER_PAGE])
    table = (f"<div class=\"table\"><table><caption>The {min(total, ROWS_PER_PAGE):,} fastest to load a page, "
             f"as ip:port. The download has all {total:,} as type://ip:port.</caption>"
             "<thead><tr><th scope=\"col\">Proxy</th><th scope=\"col\">Type</th><th scope=\"col\">Country</th>"
             "<th scope=\"col\">Latency</th><th scope=\"col\">Speed</th><th scope=\"col\">Uptime</th>"
             "<th scope=\"col\">HTTPS</th><th scope=\"col\">Gets through</th>"
             f"<th scope=\"col\">Provider</th></tr></thead><tbody>{body_rows}</tbody></table></div>"
             if total else "")
    facts = _facts(rows)
    facts_html = "" if not total else (
        "<dl class=\"facts\">"
        f"<div><dt>{facts['total']:,}</dt><dd>working right now</dd></div>"
        f"<div><dt>{facts['https']:,}</dt><dd>tunnel HTTPS</dd></div>"
        f"<div><dt>{facts['stable']:,}</dt><dd>on the list 90 %+ of the week</dd></div>"
        + (f"<div><dt>{facts['google']:,}</dt><dd>get through to Google</dd></div>"
           if facts["google"] is not None else "")
        + (f"<div><dt>{facts['speed']:,} KB/s</dt><dd>median download speed</dd></div>" if facts["speed"] else "")
        + "</dl>")
    flags = _pick_flags(path)
    # curl goes to an https:// address, so only proxies that can tunnel it
    curl_flags = flags if "--https-only" in flags else f"{flags} --https-only".strip()
    commands = (
        "<section class=\"use\"><h2>In the terminal or in code</h2>"
        f"<pre class=\"mono\">pipx install proxy-scraper-cli\nproxy-scraper --pick 5 {escape(flags)}\n"
        f"curl -x \"$(proxy-scraper --pick {escape(curl_flags)})\" https://api.ipify.org</pre>"
        "<p class=\"note\">--pick takes proxies from the same hourly list in about half a second. "
        f"From Python: <code>live_proxies()</code>, see the <a href=\"{REPO_URL}#from-python\">README</a>."
        "</p></section>")
    faq = _faq(path, facts, when)
    faq_html = "<section class=\"faq\"><h2>Questions</h2>" + "".join(
        f"<h3>{escape(q)}</h3><p>{escape(a)}</p>" for q, a in faq) + "</section>"
    faq_ld = json.dumps({"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq]},
        ensure_ascii=False).replace("</", "<\\/")
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
<style>{CSS}{PAGE_CSS}</style>
<script type="application/ld+json">{faq_ld}</script>
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
      <a class="btn" href="{root}{_list_query(path)}#list">Filter the full list</a>
      <a class="btn" href="{REPO_URL}">Check them from your network</a>
    </div>
  </main>
  {facts_html}
  {table}
  {commands}
  {faq_html}
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


def write_pages(rows: List[dict], out: Path, updated: datetime, extra: Sequence[str] = ()) -> List[str]:
    """Writes every page with its proxies.txt and the sitemap (plus the `extra` paths, e.g. the proxy pages)
    -> the paths listed in the sitemap."""
    rows = best_first(rows)
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
    listed.extend(extra)
    lastmod = updated.strftime("%Y-%m-%dT%H:%M:%S+00:00")
    urls = "".join(f"<url><loc>{SITE_URL}{p}</loc><lastmod>{lastmod}</lastmod><changefreq>hourly</changefreq></url>"
                   for p in listed)
    (out / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n'
                                     f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>\n',
                                     encoding="utf-8")
    return listed
