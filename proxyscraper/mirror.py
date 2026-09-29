"""Mirrors the hourly list into a repository of its own (runs in GitHub Actions after publish.py).

    python -m proxyscraper.mirror public/ list-repo/ --repo maximilianfeix/free-proxy-list

The proxy-list branch is also the website – thousands of HTML pages, force-pushed every hour. The list repo
only holds the lists: per protocol, per country, per site, JSON and CSV, with a README that shows the
numbers of this run. It prints the commit message; committing and pushing is up to the workflow.
Files it doesn't know (LICENSE, .github/) are left alone.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from .pages import COUNTRIES, REPO_URL, SITE_URL
from .publish import STABLE_UPTIME, num
from .sites import SITES

LISTS = (  # file, what's in it, format – in the order of the README
    ("all.txt", "All proxies", "`type://ip:port`"),
    ("http.txt", "HTTP", "`ip:port`"),
    ("socks4.txt", "SOCKS4", "`ip:port`"),
    ("socks5.txt", "SOCKS5", "`ip:port`"),
    ("https.txt", "HTTPS-capable, verified TLS", "`type://ip:port`"),
    ("elite.txt", "Elite (no forwarded IP, no Via header)", "`type://ip:port`"),
    ("stable.txt", f"Stable, on the list in {STABLE_UPTIME} %+ of this week's runs", "`type://ip:port`"),
)
MANAGED_DIRS = ("countries", "works-with")  # rewritten from scratch, so a country without proxies disappears
COUNTRY_COLUMNS = 3


def flag(cc: str) -> str:
    """DE -> 🇩🇪 (regional indicator symbols); anything that isn't two letters gets no flag."""
    if len(cc) != 2 or not cc.isalpha():
        return ""
    return "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in cc.upper())


def country_name(cc: str) -> str:
    name = COUNTRIES.get(cc.upper(), cc.upper())
    return name[4:] if name.startswith("the ") else name


def write_files(public: Path, out: Path, rows: List[dict]) -> Dict[str, int]:
    """Copies the lists, writes one list per country and a compact proxies.json. Returns lines per file."""
    for sub in MANAGED_DIRS:
        shutil.rmtree(out / sub, ignore_errors=True)
    counts: Dict[str, int] = {}
    names = [name for name, _, _ in LISTS] + [f"works-with/{s.name}.txt" for s in SITES] + ["proxies.csv"]
    for name in names:
        src = public / name
        if src.exists():
            (out / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, out / name)
            counts[name] = len(src.read_text(encoding="utf-8").splitlines())
    by_country: Dict[str, List[str]] = defaultdict(list)
    for r in rows:  # rows come best first, and so do the country lists
        if r.get("country"):
            by_country[r["country"].lower()].append(r["url"])
    (out / "countries").mkdir()
    for cc, urls in by_country.items():
        (out / "countries" / f"{cc}.txt").write_text("".join(f"{u}\n" for u in urls), encoding="utf-8")
        counts[f"countries/{cc}.txt"] = len(urls)
    # one line instead of indent=1: a third smaller, and the diff of every commit with it
    (out / "proxies.json").write_text(json.dumps(rows, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    shutil.copyfile(public / "stats.json", out / "stats.json")
    return counts


def shield(label: str, message: str, color: str, style: str = "flat-square") -> str:
    def esc(s: str) -> str:  # shields.io path: dashes and underscores are doubled, the rest percent-encoded
        return s.replace("-", "--").replace("_", "__").replace(" ", "%20").replace(",", "%2C")
    return f"https://img.shields.io/badge/{esc(label)}-{esc(message)}-{color}?style={style}&labelColor=121113"


def country_table(counts: Dict[str, int], raw: str) -> str:
    items = sorted(((name[len("countries/"):-4], n) for name, n in counts.items() if name.startswith("countries/")),
                   key=lambda kv: (-kv[1], kv[0]))
    cells = [f"{flag(cc)} {country_name(cc)} | {num(n)} | [{cc}.txt]({raw}/countries/{cc}.txt)" for cc, n in items]
    if not cells:
        return "_No country data in this run._"
    head = " | ".join(["Country | Proxies | List"] * COUNTRY_COLUMNS)
    rule = " | ".join(["---|---:|---"] * COUNTRY_COLUMNS)
    lines = [f"| {head} |", f"| {rule} |"]
    for i in range(0, len(cells), COUNTRY_COLUMNS):
        chunk = cells[i:i + COUNTRY_COLUMNS]
        chunk += [" | | "] * (COUNTRY_COLUMNS - len(chunk))
        lines.append(f"| {' | '.join(chunk)} |")
    return "\n".join(lines)


def readme(stats: dict, counts: Dict[str, int], repo: str) -> str:
    raw = f"https://raw.githubusercontent.com/{repo}/main"
    cdn = f"https://cdn.jsdelivr.net/gh/{repo}@main"
    updated = datetime.fromisoformat(stats["updated"]).strftime("%Y-%m-%d %H:%M UTC")
    by_type = stats["by_type"]
    badges = " ".join(f"![{label}]({shield(label, value, color)})" for label, value, color in (
        ("working proxies", num(stats["total"]), "D4F77A"),
        ("http", num(by_type.get("http", 0)), "blue"),
        ("socks4", num(by_type.get("socks4", 0)), "blueviolet"),
        ("socks5", num(by_type.get("socks5", 0)), "green"),
        ("updated", updated, "grey"),
    ))
    lists = "\n".join(f"| {what} | {fmt} | {num(counts.get(name, 0))} | [{name}]({raw}/{name}) · [CDN]({cdn}/{name}) |"
                      for name, what, fmt in LISTS)
    site_counts = stats.get("sites") or {}
    sites = "\n".join(f"| {s.title or s.name} | {num(counts.get(f'works-with/{s.name}.txt', 0))} | "
                      f"[{s.name}.txt]({raw}/works-with/{s.name}.txt) |"
                      for s in SITES if site_counts.get(s.name) is not None)
    sites_block = (f"""## Gets through to big sites

Many free proxies are blocked or sent to a captcha by the big sites. These got a real page in the last run:

| Site | Proxies | List |
|---|---:|---|
{sites}
""" if sites else "")
    speed = stats.get("median_speed_kbps")
    facts = [f"**{num(stats['total'])}** working proxies", f"**{num(stats['https'])}** HTTPS-capable",
             f"median latency **{num(stats['median_latency'])} ms**"]
    if speed:
        facts.append(f"median download **{num(speed)} KB/s**")
    n_countries = sum(1 for name in counts if name.startswith("countries/"))
    return f"""<div align="center">

# Free Proxy List

**HTTP, SOCKS4 and SOCKS5 proxies that worked less than an hour ago – checked, not just scraped.**

{badges}

[![Stars of the tool](https://img.shields.io/github/stars/maximilianfeix/proxy-scraper?style=social&label=proxy-scraper)]({REPO_URL})

[Download](#download) · [Quick start](#quick-start) · [By country](#by-country) · [Why this list](#why-this-list) · \
[Website]({SITE_URL}) · [The tool]({REPO_URL})

</div>

---

Updated **every hour** by [proxy-scraper]({REPO_URL}). It pulls candidates from 700+ public sources and keeps only the \
ones that pass every check – a real handshake, two sites through the same exit IP, nothing injected into the page, \
TLS that verifies. Most free lists are 95 % dead; this one is re-checked from scratch every run.

**Last run:** {updated} · {" · ".join(facts)} · {n_countries} countries

<a href="{SITE_URL}"><picture>
  <source media="(prefers-color-scheme: dark)" srcset="{SITE_URL}chart-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="{SITE_URL}chart-light.svg">
  <img src="{SITE_URL}chart-dark.svg" alt="Working proxies over the last days, by protocol" width="100%">
</picture></a>

<a id="download"></a>

## Download

Every file is sorted **best first** – by first answer plus measured download speed – so `head -n 20` gives you the \
good ones.

| List | Format | Proxies | Link |
|---|---|---:|---|
{lists}
| With all details | latency, country, provider, uptime, sites | {num(stats["total"])} | \
[proxies.json]({raw}/proxies.json) · [proxies.csv]({raw}/proxies.csv) |

Need CORS, or hitting the raw.githubusercontent rate limit? The same lists are on \
[GitHub Pages]({SITE_URL}) (e.g. `{SITE_URL}socks5.txt`), where you can also search and filter them.

<a id="quick-start"></a>

## Quick start

```bash
curl -sL {raw}/socks5.txt | head -n 20
```

```python
import requests  # pip install "requests[socks]"

proxies = requests.get("{raw}/https.txt", timeout=10).text.split()
for proxy in proxies[:20]:  # best first
    try:
        r = requests.get("https://api.ipify.org", proxies={{"http": proxy, "https": proxy}}, timeout=10)
        print(proxy, "->", r.text)
        break
    except requests.RequestException:
        continue
```

Or let [proxy-scraper]({REPO_URL}) do the rotating and retrying for you:

```bash
pip install proxy-scraper-cli
proxy-scraper --recheck live          # re-check this list from your own network (~30 s)
proxy-scraper --recheck live --serve  # ... and run it as one rotating local proxy
```

```python
from proxyscraper import ProxyRotator

with ProxyRotator(country="DE") as rotator:
    print(rotator.get("https://httpbin.org/ip").text)
```

<a id="by-country"></a>

## By country

{country_table(counts, raw)}

{sites_block}
<a id="why-this-list"></a>

## Why this list

- **Checked, not collected.** Every proxy had to complete a real protocol handshake and load two different sites \
through the same exit IP in the last run.
- **No honeypots, no injected scripts.** Pages that come back modified are thrown out; HTTPS counts only with a \
certificate that verifies.
- **Best first.** Sorted by how fast pages actually load, not by a single ping.
- **Details for every proxy** in `proxies.json`: exit IP, country, ASN and provider, datacenter or not, anonymity, \
latency, download speed, uptime over 24 hours and 7 days, first seen, and which big sites it gets through to.
- **Honest about uptime.** `stable.txt` holds only proxies that were on the list in {STABLE_UPTIME} %+ of this \
week's hourly runs.

Want more than a list? **[proxy-scraper]({REPO_URL})** is the open-source tool behind it: scan from your own \
network, filter by country, protocol and site, a rotating proxy server, a Python API and an MCP server for AI \
agents. If this list saves you time, a ⭐ on [the tool]({REPO_URL}) helps others find it.

## Good to know

- **Updates:** every hour, about 20 minutes past. A run with too few hits is skipped – the last good list stays.
- **History:** the git history is squashed at the start of every month so clones stay small. A daily archive of \
`proxies.json` lives in the [snapshot releases]({REPO_URL}/releases?q=snapshots).
- **Found a problem?** Please open an issue in the [tool repository]({REPO_URL}/issues).

> [!WARNING]
> Public proxies are run by strangers. Never send passwords or personal data through them, and use them only \
for things you're allowed to do.
"""


def commit_message(stats: dict) -> str:
    updated = datetime.fromisoformat(stats["updated"]).strftime("%Y-%m-%d %H:%M UTC")
    return f"{num(stats['total'])} working proxies · {updated}"


def mirror(public: Path, out: Path, repo: str) -> str:
    rows = json.loads((public / "proxies.json").read_text(encoding="utf-8"))
    stats = json.loads((public / "stats.json").read_text(encoding="utf-8"))
    out.mkdir(parents=True, exist_ok=True)
    counts = write_files(public, out, rows)
    (out / "README.md").write_text(readme(stats, counts, repo), encoding="utf-8")
    return commit_message(stats)


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="copy the published lists into a list-only repository")
    p.add_argument("public_dir", type=Path, help="what publish.py wrote")
    p.add_argument("repo_dir", type=Path, help="a checkout of the list repository")
    p.add_argument("--repo", default="maximilianfeix/free-proxy-list", help="owner/name, for the links")
    args = p.parse_args(argv)
    print(mirror(args.public_dir, args.repo_dir, args.repo))
    return 0


if __name__ == "__main__":
    sys.exit(main())
