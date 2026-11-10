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


CHECKS = (  # name in stats.json -> heading and what a pass means; {basic}/{confirm} are this run's test hosts
    ("basic", "Handshake", "The proxy completed a real handshake and fetched a page from {basic}. The exit IP it "
                           "showed was public and not the checker's own."),
    ("confirm", "Second request", "A second request, to an unrelated site ({confirm}), came out of the same exit IP. "
                                  "Proxies that answer once and then stall or switch exits drop out here."),
    ("content", "Unchanged page", "A known static page ({confirm}/html) arrived byte for byte. A proxy that rewrites "
                                  "plain-HTTP pages, e.g. injects ads or scripts, fails. It covers that one page at "
                                  "that moment, nothing more."),
    ("https", "Verified TLS", "A tunnel to port 443 with a TLS handshake whose certificate verified on one test host "
                              "({basic}). It says nothing about other sites, later requests or who runs the proxy."),
)


def checks_table(stats: dict, run: dict) -> str:
    """What each check means, which lists need it and how many proxies passed it in this run (run.json)."""
    requires: Dict[str, List[str]] = stats.get("requires") or {}
    targets = run.get("targets") or {}
    hosts = {"basic": targets.get("basic") or "a test host", "confirm": targets.get("confirm") or "a second test host"}
    results = run.get("checks") or {}
    lines = ["| Check | What a pass means | Needed for | Passed in this run |", "|---|---|---|---:|"]
    for name, title, text in CHECKS:
        needed = [f for f, checks in requires.items() if name in checks]
        if not needed:
            continue
        where = "every list" if len(needed) == len(requires) else ", ".join(f"`{f}`" for f in needed)
        passed = (results.get(name) or {}).get("passed")
        lines.append(f"| **{title}** | {text.format(**hosts)} | {where} | "
                     f"{num(passed) if isinstance(passed, int) else '–'} |")
    return "\n".join(lines) if len(lines) > 2 else ""


def star_history(repo: str) -> str:
    tool = REPO_URL.removeprefix("https://github.com/")
    return (f"[![Star history](https://api.star-history.com/svg?repos={repo},{tool}&type=Date)]"
            f"(https://star-history.com/#{repo}&{tool}&Date)")


def readme(stats: dict, counts: Dict[str, int], repo: str, run: Optional[dict] = None,
           sources: Optional[int] = None) -> str:
    run = run or {}
    raw = f"https://raw.githubusercontent.com/{repo}/main"
    cdn = f"https://cdn.jsdelivr.net/gh/{repo}@main"
    updated = datetime.fromisoformat(stats["updated"]).strftime("%Y-%m-%d %H:%M UTC")
    by_type = stats["by_type"]
    hours = stats.get("run_hours")
    every = "every hour" if hours == 1 else f"every {hours} hours" if isinstance(hours, int) and hours > 1 else ""
    badge_values = [
        ("working proxies", num(stats["total"]), "D4F77A"),
        ("http", num(by_type.get("http", 0)), "blue"),
        ("socks4", num(by_type.get("socks4", 0)), "blueviolet"),
        ("socks5", num(by_type.get("socks5", 0)), "green"),
        ("updated", updated, "grey"),
    ]
    if every:
        badge_values.append(("checked", every, "grey"))
    badges = " ".join(f"![{label}]({shield(label, value, color)})" for label, value, color in badge_values)
    stars = (f"[![Stars](https://img.shields.io/github/stars/{repo}?style=social)](https://github.com/{repo}) "
             f"[![Stars of the tool](https://img.shields.io/github/stars/maximilianfeix/proxy-scraper"
             f"?style=social&label=proxy-scraper)]({REPO_URL})")
    lists = "\n".join(f"| {what} | {fmt} | {num(counts.get(name, 0))} | [GitHub]({raw}/{name}) · [CDN]({cdn}/{name}) · "
                      f"[proxy-scraper.de]({SITE_URL}{name}) |" for name, what, fmt in LISTS)
    copy_urls = "\n".join(f"{raw}/{name}" for name in ("all.txt", "http.txt", "socks4.txt", "socks5.txt"))
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
    checked = run.get("checked")
    if isinstance(checked, int) and checked > 0:
        origin = f", collected from **{num(sources)}** tracked public sources" if sources else ""
        funnel = (f"This run checked **{num(checked)}** candidates{origin}. **{num(stats['total'])}** "
                  f"({stats['total'] / checked:.2%}) passed every check and made the list.")
    else:
        funnel = f"**{num(stats['total'])}** proxies passed every check in this run and made the list."
    checks = checks_table(stats, run)
    checks_block = (f"""<a id="checks"></a>

## What the checks mean

{checks}

A pass means the proxy worked **from our checker, at that moment**. Free proxies come and go, so expect some entries \
to be gone by the time you use them. Take the top of a file and skip what fails.
""" if checks else "")
    checks_link = " · [Checks](#checks)" if checks else ""
    return f"""<div align="center">

# Free Proxy List

**{num(stats['total'])} free HTTP, SOCKS4 and SOCKS5 proxies that passed every check, re-checked \
{every or "regularly"}. Plain text files, no signup, no API key.**

{badges}

{stars}

[Download](#download) · [Usage](#quick-start) · [By country](#by-country){checks_link} · \
[Why this list](#why-this-list) · [Website]({SITE_URL}) · [The tool]({REPO_URL})

</div>

---

```text
{copy_urls}
```

<sub>`http.txt`, `socks4.txt` and `socks5.txt` hold one `ip:port` per line, `all.txt` one `type://ip:port`. Best \
first. The same files are at `{SITE_URL}<name>.txt` and on the [jsDelivr CDN]({cdn}/all.txt).</sub>

**Last run:** {updated} · {" · ".join(facts)} · {n_countries} countries

{funnel}

<a id="download"></a>

## Download

Every file is sorted **best first** (first answer plus measured download speed), so `head -n 20` gives you the \
good ones. Hitting the raw.githubusercontent rate limit or need CORS? Use the CDN or proxy-scraper.de link.

| List | Format | Proxies | Download |
|---|---|---:|---|
{lists}
| With all details | latency, country, provider, uptime, sites | {num(stats["total"])} | \
[proxies.json]({raw}/proxies.json) · [proxies.csv]({raw}/proxies.csv) |

<a href="{SITE_URL}"><picture>
  <source media="(prefers-color-scheme: dark)" srcset="{SITE_URL}chart-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="{SITE_URL}chart-light.svg">
  <img src="{SITE_URL}chart-dark.svg" alt="Working proxies over the last days, by protocol" width="100%">
</picture></a>

<a id="quick-start"></a>

## Usage

### curl

```bash
curl -sL {raw}/socks5.txt | head -n 20  # the 20 best SOCKS5 proxies
curl -m 10 -x "socks5h://$(curl -sL {raw}/socks5.txt | head -n 1)" https://api.ipify.org
```

### wget

```bash
wget -qO http.txt {raw}/http.txt
```

### Python

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

<details>
<summary><b>Node.js and Go</b></summary>

### Node.js

```javascript
// needs "type": "module" in package.json or .mjs
import {{ fetch, ProxyAgent }} from 'undici';  // npm install undici
// Note: ProxyAgent only speaks HTTP(S) proxies; socks4:// and socks5:// lines will be skipped by the loop

const response = await fetch("{raw}/https.txt");
const proxies = (await response.text()).split("\\n");
for (const proxy of proxies.slice(0, 20)) {{
    try {{
        const r = await fetch("https://api.ipify.org", {{
            dispatcher: new ProxyAgent(proxy.trim()),
            signal: AbortSignal.timeout(10_000)
        }});
        console.log(proxy.trim(), "->", await r.text());
        break;
    }} catch {{}}
}}
```

### Go

```go
package main

import (
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"
)

func main() {{
	resp, err := http.Get("{raw}/https.txt")
	if err != nil {{
		return
	}}
	defer resp.Body.Close()
	body, _ := io.ReadAll(resp.Body)
	proxies := strings.Fields(string(body))
	if len(proxies) > 20 {{
		proxies = proxies[:20]
	}}
	for _, proxy := range proxies {{
		proxyURL, err := url.Parse(proxy)
		if err != nil {{
			continue
		}}
		client := &http.Client{{
			Timeout:   10 * time.Second,
			Transport: &http.Transport{{Proxy: http.ProxyURL(proxyURL)}},
		}}
		if r, err := client.Get("https://api.ipify.org"); err == nil {{
			ip, _ := io.ReadAll(r.Body)
			r.Body.Close()
			fmt.Printf("%s -> %s\\n", proxy, ip)
			break
		}}
	}}
}}
```

</details>

Or let [proxy-scraper]({REPO_URL}) do the rotating and retrying for you:

```bash
pip install proxy-scraper-cli
proxy-scraper --pick 3 --verify       # three entries of this list that pass right now, from your network
proxy-scraper --diagnose HOST:PORT    # why one entry works for you or doesn't: every check and what it found
proxy-scraper --recheck live --serve  # re-check the whole list from here and run it as one rotating local proxy
```

```python
from proxyscraper import ProxyRotator

with ProxyRotator(country="DE") as rotator:
    print(rotator.get("https://httpbin.org/ip").text)
```

<a id="by-country"></a>

## By country

One file per country, best first, as `type://ip:port`: `{raw}/countries/<code>.txt` \
(also at `{SITE_URL}country/<code>/proxies.txt`).

{country_table(counts, raw)}

{sites_block}
{checks_block}
<a id="why-this-list"></a>

## Why this list

- **Checked, not just collected.** Every entry completed a real handshake and loaded two different sites through the \
same exit IP in the last run.
- **A test page has to arrive unchanged.** Entries that returned a changed test page are left out; HTTPS counts only \
with a certificate that verified on the test host.
- **Best first.** Sorted by how fast pages actually load, not by a single ping.
- **Details for every proxy** in `proxies.json`: exit IP, country, ASN and provider, whether the provider looks like a \
hosting company, anonymity, latency, download speed, share of runs on the list over 24 hours and 7 days, \
first seen, and which big sites it gets through to.
- **Share of runs on the list.** `stable.txt` holds only proxies that were on the list in {STABLE_UPTIME} %+ of this \
week's runs. Not being on the list is not a measured failure.
- **Used by other tools.** [monosans/proxy-scraper-checker](https://github.com/monosans/proxy-scraper-checker) \
and [gfpcom/free-proxy-list](https://github.com/gfpcom/free-proxy-list) pull these lists as a built-in source.

## Support

If this list saves you time, a ⭐ helps others find it. A star on **[proxy-scraper]({REPO_URL})** counts too: \
it's the open-source tool that builds this list. Run it to scan from your own network, filter by country, protocol \
and site, or use its rotating proxy server, Python API and MCP server for AI agents.

{star_history(repo)}

## Good to know

- **Updates:** {every or "regularly"}, around 20 minutes past. A run with too few hits is skipped and the last \
good list stays.
- **History:** the git history is squashed at the start of every month so clones stay small. A daily archive of \
`proxies.json` lives in the [snapshot releases]({REPO_URL}/releases?q=snapshots).
- **Found a problem?** Please open an issue in the [tool repository]({REPO_URL}/issues).

> [!WARNING]
> Public proxies are run by strangers. Never send passwords or personal data through them, and use them only \
for things you're allowed to do.
"""


def optional_json(path: Path) -> Optional[dict]:
    """run.json and sources.json only add numbers to the README – a run without them still gets one."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def commit_message(stats: dict) -> str:
    updated = datetime.fromisoformat(stats["updated"]).strftime("%Y-%m-%d %H:%M UTC")
    return f"{num(stats['total'])} working proxies · {updated}"


def mirror(public: Path, out: Path, repo: str) -> str:
    rows = json.loads((public / "proxies.json").read_text(encoding="utf-8"))
    stats = json.loads((public / "stats.json").read_text(encoding="utf-8"))
    out.mkdir(parents=True, exist_ok=True)
    counts = write_files(public, out, rows)
    run = optional_json(public / "run.json")
    sources = (optional_json(public / "sources.json") or {}).get("sources")
    (out / "README.md").write_text(readme(stats, counts, repo, run=run,
                                          sources=len(sources) if isinstance(sources, list) else None),
                                   encoding="utf-8")
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
