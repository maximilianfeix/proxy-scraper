"""A page per proxy on the live list: what it is, how reliable it has been this week, which big sites let it
through, and the commands to try it yourself.

Only proxies that were on the list for at least half of the week's runs are indexed – thousands of pages that
come and go every hour would look like spam to search engines. The others get a page too, with noindex.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from .pages import COUNTRIES, CSS, SITE_URL, _short_name

INDEX_MIN_UPTIME = 50  # percent of the week's runs
SITE_NAMES = {"google": "Google", "reddit": "Reddit", "amazon": "Amazon"}

EXTRA_CSS = """
.wrap > * { min-width: 0; }
h1.mono { font-size: clamp(28px, 7vw, 64px); letter-spacing: -.03em; overflow-wrap: anywhere; }
.facts { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 160px), 1fr)); gap: 1px;
         background: var(--line);
         border: 1px solid var(--line); border-radius: 16px; overflow: hidden; margin: 0; }
.facts div { background: var(--panel); padding: 14px 16px; }
.facts dt { color: var(--muted); font-size: 13px; }
.facts dd { margin: 4px 0 0; font-size: 17px; }
h2 { font-size: 22px; letter-spacing: -.02em; margin: 0 0 12px; font-weight: 600; }
.timeline { display: flex; gap: 2px; align-items: stretch; height: 34px; }
.cell { flex: 1; min-width: 2px; border-radius: 2px; background: var(--line); }
.cell.on { background: var(--signal-ink); }
.axis { display: flex; justify-content: space-between; color: var(--muted); font-size: 13px; margin-top: 6px; }
.cmd code { white-space: pre-wrap; word-break: break-all; }
.cmd { position: relative; background: var(--panel); border: 1px solid var(--line); border-radius: 12px;
       padding: 12px 56px 12px 14px; margin: 0 0 10px; overflow-x: auto; font-size: 14px; }
.cmd button { position: absolute; top: 8px; right: 8px; font: inherit; font-size: 13px; padding: 4px 10px;
              border-radius: 99px; border: 1px solid var(--line); background: var(--bg); color: var(--text);
              cursor: pointer; }
.lede { overflow-wrap: anywhere; }
.note { color: var(--muted); font-size: 14px; }
.status { display: inline-flex; align-items: center; gap: 8px; color: var(--muted); }
.status::before { content: ""; width: 9px; height: 9px; border-radius: 50%; background: var(--signal-ink); }
"""

COPY_JS = """<script>
document.querySelectorAll(".cmd button").forEach(b => b.onclick = () => {
  navigator.clipboard.writeText(b.previousElementSibling.textContent).then(() => {
    b.textContent = "Copied"; setTimeout(() => { b.textContent = "Copy"; }, 1500);
  });
});
</script>"""


def page_path(proxy: str) -> str:
    """'1.2.3.4:1080' -> 'proxy/1.2.3.4-1080/'"""
    return "proxy/" + proxy.replace(":", "-") + "/"


def _country(cc: str) -> str:
    return _short_name(COUNTRIES[cc]) if cc in COUNTRIES else (cc or "unknown")


def _commands(row: dict) -> List[str]:
    target = "https://api.ipify.org" if row.get("https") else "http://api.ipify.org"
    scheme = "socks5h" if row["ptype"] == "socks5" else row["ptype"]  # socks5h: DNS through the proxy too
    return [f"curl -x {scheme}://{row['proxy']} {target}",
            f'python -c "import requests; print(requests.get(\'{target}\', '
            f'proxies={{\'http\': \'{row["url"]}\', \'https\': \'{row["url"]}\'}}, timeout=10).text)"']


def _cmd(command: str) -> str:
    return f'<div class="cmd"><code class="mono">{escape(command)}</code><button type="button">Copy</button></div>'


def _timeline(bits: Optional[int], runs: Sequence[datetime]) -> str:
    """One cell per run of the week, oldest left – filled where the proxy was on the list."""
    if bits is None or not runs:
        return ""
    cells = "".join(f'<span class="cell{" on" if bits >> k & 1 else ""}"></span>'
                    for k in range(len(runs) - 1, -1, -1))  # bit 0 = the newest run
    first = runs[0].strftime("%b %d, %H:%M UTC")
    return (f'<section aria-label="Timeline"><h2>Every check this week</h2>'
            f'<div class="timeline" role="img" aria-label="On the list in {bin(bits).count("1")} '
            f'of the last {len(runs)} hourly checks">{cells}</div>'
            f'<div class="axis"><span>{escape(first)}</span><span>now</span></div></section>')


def _render(proxy: str, entries: List[dict], updated: datetime, bits: Optional[int], runs: Sequence[datetime],
            indexed: bool) -> str:
    root = "../../"
    best = min(entries, key=lambda r: r["latency"])
    urls = " · ".join(escape(r["url"]) for r in entries)
    cc = best.get("country") or ""
    through = [SITE_NAMES[k] for k, ok in (best.get("sites") or {}).items() if ok and k in SITE_NAMES]
    uptime = best.get("uptime_7d")
    facts = [
        ("Protocol", ", ".join(r["ptype"].upper() for r in entries)),
        ("Country", f"{_country(cc)}"),
        ("Provider", f"{best.get('org') or 'unknown'}" + (f" (AS{best['asn']})" if best.get("asn") else "")),
        ("Latency", f"{best['latency']:,} ms"),
        ("HTTPS", "yes, verified TLS" if best.get("https") else "no"),
        ("Anonymity", best.get("anonymity") or "unknown"),
        ("Uptime this week", f"{uptime} %" if uptime is not None else "not measured yet"),
        ("Gets through to", ", ".join(through) if through else "none of the checked sites"),
        ("Datacenter exit", "yes" if best.get("hosting") else "no" if best.get("hosting") is False else "unknown"),
        ("Spam blocklist", "listed" if best.get("blocklisted") else "not listed"
         if best.get("blocklisted") is False else "unknown"),
        ("First seen", (best.get("first_seen") or "")[:16].replace("T", " ") + " UTC" if best.get("first_seen")
         else "unknown"),
        ("Exit IP", best.get("exit_ip") or "unknown"),
    ]
    facts_html = "".join(f"<div><dt>{escape(k)}</dt><dd>{escape(v)}</dd></div>" for k, v in facts)
    commands = "".join(_cmd(_commands(r)[0]) for r in entries)
    python = _commands(best)[1]
    title = f"{best['ptype'].upper()} proxy {proxy} ({_country(cc)})"
    reliability = f", on the list in {uptime} % of this week's hourly checks" if uptime is not None else ""
    description = (f"Free {', '.join(r['ptype'].upper() for r in entries)} proxy {proxy} in {_country(cc)}"
                   f"{reliability}. Latency, provider, HTTPS support and commands to test it.")
    robots = "" if indexed else '<meta name="robots" content="noindex">\n'
    checked = updated.strftime("%Y-%m-%d %H:%M UTC")
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)} | proxy-scraper</title>
<meta name="description" content="{escape(description)}">
{robots}<link rel="canonical" href="{SITE_URL}{page_path(proxy)}">
<link rel="icon" href="{root}logo.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Geist:wght@400..700&family=Geist+Mono:wght@400;500&display=swap"
      rel="stylesheet">
<link rel="stylesheet" href="../style.css">
</head>
<body>
<div class="wrap">
  <header>
    <a class="brand" href="{root}"><img src="{root}logo.png" alt="">proxy-scraper</a>
    <a href="{root}?country={escape(cc)}#list">All proxies in {escape(_country(cc))}</a>
  </header>
  <main>
    <h1 class="mono">{escape(proxy)}</h1>
    <p class="lede"><span class="status">Worked in the check at {escape(checked)}</span><br>{urls}</p>
  </main>
  <dl class="facts">{facts_html}</dl>
  {_timeline(bits, runs)}
  <section aria-label="Test it"><h2>Test it from your machine</h2>
    <p class="note">Free proxies come and go, and some behave differently from your network. This prints the IP
    a website sees – the proxy's, if it works.</p>
    {commands}
    {_cmd(python)}
    <p class="note">Never send passwords or personal data through a public proxy. Its operator can read everything
    that isn't encrypted.</p>
  </section>
  <footer><span>Checked every hour by <a href="https://github.com/maximilianfeix/proxy-scraper">proxy-scraper</a>,
  open source.</span></footer>
</div>
{COPY_JS}
</body>
</html>
"""


def write_proxy_pages(rows: List[dict], out: Path, updated: datetime, timelines: Dict[str, int],
                      runs: Sequence[datetime]) -> List[str]:
    """A page per ip:port -> the paths that should be in the sitemap (the reliable ones).

    timelines: url -> bits (bit 0 = this run), runs: the times of the week's runs, oldest first."""
    (out / "proxy").mkdir(parents=True, exist_ok=True)
    (out / "proxy" / "style.css").write_text(CSS + EXTRA_CSS, encoding="utf-8")  # shared: ~1,500 pages
    by_address: Dict[str, List[dict]] = defaultdict(list)
    for r in rows:
        by_address[r["proxy"]].append(r)
    indexed = []
    for proxy, entries in by_address.items():
        entries.sort(key=lambda r: r["ptype"])
        uptime = max((r.get("uptime_7d") or 0) for r in entries) if any(r.get("uptime_7d") is not None
                                                                         for r in entries) else None
        is_indexed = uptime is not None and uptime >= INDEX_MIN_UPTIME
        bits = None
        for r in entries:
            if r["url"] in timelines:
                bits = (bits or 0) | timelines[r["url"]]
        folder = out / page_path(proxy)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "index.html").write_text(_render(proxy, entries, updated, bits, runs, is_indexed), encoding="utf-8")
        if is_indexed:
            indexed.append(page_path(proxy))
    return sorted(indexed)
