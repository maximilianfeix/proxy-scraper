<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/banner-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="docs/banner-light.svg">
  <img src="docs/banner-dark.svg" alt="proxy-scraper – free proxies that actually work" width="100%">
</picture>

[![tests](https://github.com/maximilianfeix/proxy-scraper/actions/workflows/tests.yml/badge.svg)](https://github.com/maximilianfeix/proxy-scraper/actions/workflows/tests.yml)
[![Release](https://img.shields.io/github/v/release/maximilianfeix/proxy-scraper?style=flat-square&color=D4F77A&labelColor=121113)](https://github.com/maximilianfeix/proxy-scraper/releases/latest)
[![Live proxies](https://img.shields.io/endpoint?url=https%3A%2F%2Fraw.githubusercontent.com%2Fmaximilianfeix%2Fproxy-scraper%2Fproxy-list%2Fbadges%2Ftotal.json&style=flat-square&labelColor=121113)](#live-list)
[![Python](https://img.shields.io/badge/python-3.9–3.13-D4F77A?style=flat-square&labelColor=121113)](pyproject.toml)
[![License](https://img.shields.io/badge/license-MIT-D4F77A?style=flat-square&labelColor=121113)](LICENSE)

<a href="https://maximilianfeix.github.io/proxy-scraper/"><img src="https://img.shields.io/badge/Browse_the_live_list-D4F77A?style=for-the-badge&labelColor=121113" alt="Browse the live list"></a>
<a href="#install"><img src="https://img.shields.io/badge/Install-121113?style=for-the-badge" alt="Install"></a>
<a href="#from-python"><img src="https://img.shields.io/badge/Python_API-121113?style=for-the-badge" alt="Python API"></a>
<a href="#mcp"><img src="https://img.shields.io/badge/MCP_server-121113?style=for-the-badge" alt="MCP server for AI agents"></a>
<a href="bot/"><img src="https://img.shields.io/badge/Discord_bot-121113?style=for-the-badge" alt="Discord bot"></a>

[Install](#install) · [Live list](#live-list) · [For AI agents](#mcp) · [Proxy server](#proxy-server) · [How it works](#how-it-works) · [Recipes](#recipes) · [Options](#options) · [FAQ](#faq)

</div>

---

Most free proxy lists are 95 % dead, and a good part of the rest are honeypots or proxies that inject scripts into your pages. **proxy-scraper** collects public HTTP, SOCKS4 and SOCKS5 proxies from 700+ sources and keeps only the ones that pass every check. It learns with every run which sources are worth it, and it can turn the result into a single rotating proxy.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/checks-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="docs/checks-light.svg">
  <img src="docs/checks-dark.svg" alt="The five checks: 700+ lists, a real handshake, two sites with one IP, nothing injected, the details" width="100%">
</picture>

<div align="center">
<img src="docs/demo.svg" alt="Animated demo: setup wizard, collecting, live dashboard and final report" width="880">
</div>

<details>
<summary><b>Table of contents</b></summary>

- [Install](#install)
- [Live proxy list](#live-list)
- [For AI agents (MCP)](#mcp)
- [Features](#features) · [Why not just download a list?](#why-not-just-download-a-list)
- [Examples](#examples)
- [Recipes](#recipes)
- [Rotating proxy server](#proxy-server)
- [Discord bot](#discord-bot)
- [How it works](#how-it-works)
- [Output](#output)
- [Options](#options)
- [GitHub Actions](#github-actions)
- [FAQ](#faq)
- [Roadmap](#roadmap) · [Contributing](#contributing) · [Acknowledgements](#acknowledgements)

</details>

<a id="install"></a>

## Install

**With [pipx](https://pipx.pypa.io/)** (recommended – gives you a `proxy-scraper` command in its own environment):

```bash
pipx install git+https://github.com/maximilianfeix/proxy-scraper.git
proxy-scraper
```

<details>
<summary><b>Other ways: Docker, pip, a faster event loop, or straight from the repo</b></summary>
<br>

```bash
# Docker – learned state and results stay in two folders next to you
mkdir -p proxy-data results
docker run --rm --user "$(id -u):$(id -g)" -v "$PWD/proxy-data:/data" -v "$PWD/results:/work/results" \
  ghcr.io/maximilianfeix/proxy-scraper --want 50 --https-only

# pip into the current environment
pip install git+https://github.com/maximilianfeix/proxy-scraper.git

# optional: faster event loop on macOS/Linux
pipx install "proxy-scraper[fast] @ git+https://github.com/maximilianfeix/proxy-scraper.git"

# no install at all
git clone https://github.com/maximilianfeix/proxy-scraper.git
cd proxy-scraper
pip install -r requirements.txt
python3 proxy_scraper.py
```

Every [release](https://github.com/maximilianfeix/proxy-scraper/releases/latest) also ships a wheel you can install with `pip install <file>.whl`, and a multi-arch image (amd64/arm64) on `ghcr.io`. In the container the wizard never shows up, it runs straight away. For the proxy server use `--serve --serve-host 0.0.0.0` with `-p 127.0.0.1:8899:8899`, so the port is only open on your own machine.

Tab completion for bash, zsh and fish:

```bash
eval "$(proxy-scraper --completion zsh)"     # in ~/.zshrc (after compinit), same for bash in ~/.bashrc
proxy-scraper --completion fish > ~/.config/fish/completions/proxy-scraper.fish
```

Installed, the learned state lives in your user data folder (`~/Library/Application Support/proxy-scraper`, `%LOCALAPPDATA%\proxy-scraper` or `~/.local/share/proxy-scraper`; override with `PROXY_SCRAPER_HOME`) and results go to `./results`. Run from a clone, both stay inside the project.

</details>

Started without arguments, a wizard asks what you are looking for:

<div align="center">
<img src="docs/wizard.svg" alt="Setup wizard" width="760">
</div>

| Preset | What it does |
|---|---|
| **Find everything** | all protocols, maximum yield |
| **Browsing & web** | HTTP + SOCKS5, HTTPS-capable, at least anonymous, under 3 s |
| **Maximum anonymity** | elite SOCKS5 with HTTPS only |
| **Fast & stable** | proxies under 1 s only |
| **A few right now** | stops after 25 hits |
| **Recheck the last hits** | no collecting, takes seconds |
| **Proxy server right away** | recheck the last hits, then serve them on :8899 |
| **Same as last time** | your previous choice |
| **Custom …** | protocols, countries, anonymity, HTTPS, target site, latency, amount, check mode |

Keys: <kbd>↑</kbd><kbd>↓</kbd> select · <kbd>Space</kbd> toggle · <kbd>1</kbd>–<kbd>9</kbd> jump · <kbd>Enter</kbd> next · <kbd>Esc</kbd> back · <kbd>q</kbd> quit. In scripts and cron jobs the wizard never shows up – pass options or `-y`.

<a id="live-list"></a>

## Live proxy list

Don't want to scan yourself? Every hour **GitHub Actions** runs the tool and publishes the hits to the [`proxy-list`](../../tree/proxy-list) branch – every entry worked in the last run, fastest first.

**→ [Browse it on the website](https://maximilianfeix.github.io/proxy-scraper/)** – search, filter by type, country, HTTPS, provider and latency, see how long each proxy has been up, copy or download exactly the proxies you need. `streaks.json` on the branch has the number of runs in a row for every proxy.

Every protocol and country also has its own page with a plain download, e.g. [SOCKS5](https://maximilianfeix.github.io/proxy-scraper/socks5/) or [Germany](https://maximilianfeix.github.io/proxy-scraper/country/de/) (`country/de/proxies.txt`).

<div align="center"><a href="https://maximilianfeix.github.io/proxy-scraper/"><img src="docs/website.png" alt="The live list website" width="860"></a></div>

<div align="center">

[![Proxies](https://img.shields.io/endpoint?url=https%3A%2F%2Fraw.githubusercontent.com%2Fmaximilianfeix%2Fproxy-scraper%2Fproxy-list%2Fbadges%2Ftotal.json&style=for-the-badge)](../../tree/proxy-list)
[![HTTP](https://img.shields.io/endpoint?url=https%3A%2F%2Fraw.githubusercontent.com%2Fmaximilianfeix%2Fproxy-scraper%2Fproxy-list%2Fbadges%2Fhttp.json&style=for-the-badge)](https://raw.githubusercontent.com/maximilianfeix/proxy-scraper/proxy-list/http.txt)
[![SOCKS4](https://img.shields.io/endpoint?url=https%3A%2F%2Fraw.githubusercontent.com%2Fmaximilianfeix%2Fproxy-scraper%2Fproxy-list%2Fbadges%2Fsocks4.json&style=for-the-badge)](https://raw.githubusercontent.com/maximilianfeix/proxy-scraper/proxy-list/socks4.txt)
[![SOCKS5](https://img.shields.io/endpoint?url=https%3A%2F%2Fraw.githubusercontent.com%2Fmaximilianfeix%2Fproxy-scraper%2Fproxy-list%2Fbadges%2Fsocks5.json&style=for-the-badge)](https://raw.githubusercontent.com/maximilianfeix/proxy-scraper/proxy-list/socks5.txt)
[![Updated](https://img.shields.io/endpoint?url=https%3A%2F%2Fraw.githubusercontent.com%2Fmaximilianfeix%2Fproxy-scraper%2Fproxy-list%2Fbadges%2Fupdated.json&style=for-the-badge)](../../actions/workflows/proxy-list.yml)

</div>

| List | Format | Link |
|---|---|---|
| All | `socks5://1.2.3.4:1080` | [all.txt](https://raw.githubusercontent.com/maximilianfeix/proxy-scraper/proxy-list/all.txt) |
| HTTP · SOCKS4 · SOCKS5 | `1.2.3.4:8080` | [http.txt](https://raw.githubusercontent.com/maximilianfeix/proxy-scraper/proxy-list/http.txt) · [socks4.txt](https://raw.githubusercontent.com/maximilianfeix/proxy-scraper/proxy-list/socks4.txt) · [socks5.txt](https://raw.githubusercontent.com/maximilianfeix/proxy-scraper/proxy-list/socks5.txt) |
| HTTPS-capable only | `type://ip:port` | [https.txt](https://raw.githubusercontent.com/maximilianfeix/proxy-scraper/proxy-list/https.txt) |
| Elite only | `type://ip:port` | [elite.txt](https://raw.githubusercontent.com/maximilianfeix/proxy-scraper/proxy-list/elite.txt) |
| With all details | latency, country, HTTPS, anonymity, exit IP | [proxies.json](https://raw.githubusercontent.com/maximilianfeix/proxy-scraper/proxy-list/proxies.json) · [proxies.csv](https://raw.githubusercontent.com/maximilianfeix/proxy-scraper/proxy-list/proxies.csv) |

```bash
curl -s https://raw.githubusercontent.com/maximilianfeix/proxy-scraper/proxy-list/socks5.txt | head
```

Or let the tool start from it: `proxy-scraper --recheck live` downloads the list and checks it again from **your** network – about 30 seconds instead of a full scan (517 of 1,169 worked from here). With `--serve` you have a rotating proxy in under a minute.

<a id="mcp"></a>

## For AI agents (MCP)

<!-- mcp-name: io.github.maximilianfeix/proxy-scraper -->

`proxy-scraper-mcp` is an [MCP](https://modelcontextprotocol.io) server: Claude Code, Claude Desktop, Cursor, VS Code, Codex and any other MCP client can ask for working proxies and load pages through them.

| Tool | What it does |
|---|---|
| `get_proxies` | working proxies right now, from the hourly list – filter by protocol, country, HTTPS, elite, no datacenter, not blocklisted, stable, latency |
| `check_proxies` | checks proxies from your own network, so they work from where your code runs (30–90 s, reports progress) |
| `fetch_url` | loads a page through a verified proxy, switches proxies by itself when one fails, returns readable text – HTTPS only through proxies with verified TLS |

Things to ask your agent: *"Load bbc.com/news as seen from the UK"*, *"Give me 5 SOCKS5 proxies from Germany that aren't in a datacenter"*, *"Check which of these sites block free proxies"*.

Needs Python 3.10+ and [uv](https://docs.astral.sh/uv/). **Claude Code:**

```bash
claude mcp add proxy-scraper -- uvx --from "proxy-scraper[mcp] @ git+https://github.com/maximilianfeix/proxy-scraper" proxy-scraper-mcp
```

**Claude Desktop, Cursor and most other clients** – add this to the MCP config (Claude Desktop: Settings → Developer → Edit Config, Cursor: `~/.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "proxy-scraper": {
      "command": "uvx",
      "args": ["--from", "proxy-scraper[mcp] @ git+https://github.com/maximilianfeix/proxy-scraper", "proxy-scraper-mcp"]
    }
  }
}
```

<details>
<summary><b>VS Code, Codex, or without uv</b></summary>

**VS Code** – `.vscode/mcp.json`:

```json
{
  "servers": {
    "proxy-scraper": {
      "type": "stdio",
      "command": "uvx",
      "args": ["--from", "proxy-scraper[mcp] @ git+https://github.com/maximilianfeix/proxy-scraper", "proxy-scraper-mcp"]
    }
  }
}
```

**Codex** – `~/.codex/config.toml`:

```toml
[mcp_servers.proxy-scraper]
command = "uvx"
args = ["--from", "proxy-scraper[mcp] @ git+https://github.com/maximilianfeix/proxy-scraper", "proxy-scraper-mcp"]
```

**Without uv:** `pipx install "proxy-scraper[mcp] @ git+https://github.com/maximilianfeix/proxy-scraper"`, then use `proxy-scraper-mcp` as the command.

</details>

The server tells agents what it tells you: free proxies are run by strangers, so no logins, cookies or personal data through them. Local and private addresses are refused, and results go to proxy-scraper's data folder, not into the project you're working in.

<a id="features"></a>

## Features

<table>
<tr>
<td width="50%" valign="top">

**Setup wizard**<br>
Started without arguments, the tool asks what you need using the arrow keys – a preset or step by step. At the end it shows the matching command line.

</td>
<td width="50%" valign="top">

**Fast**<br>
700+ sources fetched in parallel, large lists parsed on all CPU cores, hand-written HTTP/SOCKS handshakes directly on `asyncio` with 2000+ checks at once.

</td>
</tr>
<tr>
<td valign="top">

**Real verification**<br>
Every hit has to fetch two independent pages – that weeds out **honeypots** that only answer check requests (in some runs 5 out of 6 “hits”). A third request catches proxies that **tamper with content**: in our measurements one in five working proxies injected a script into a plain HTML page. Plus: HTTPS through a tunnel with **verified TLS**, anonymity level *elite / anonymous / transparent* and the country of the exit IP.

</td>
<td valign="top">

**Learns with every run**<br>
Hit rate per source, history of working proxies, automatic removal of dead and stale lists. With `-l 5000` you get the *best* 5000 candidates, not just any.

</td>
</tr>
<tr>
<td valign="top">

**Finds new sources by itself**<br>
Searches GitHub for actively maintained proxy lists and reads source lists maintained by others. Spam clone farms and plain mirrors are detected.

</td>
<td valign="top">

**Filters & target sites**<br>
With `--target google.com` a proxy only counts if it really reaches the site – many public proxies are blocked by Google, Discord & co. Filter by country, HTTPS, anonymity and latency, and stop with `--want 50` as soon as enough matching proxies are found. Filters even speed things up: with `--max-latency 1000` slow proxies are given up after 1 s instead of 8 s.

</td>
</tr>
<tr>
<td valign="top">

**Live dashboard**<br>
Speed chart, latency histogram, protocols, countries and the latest hits in real time. <kbd>Ctrl</kbd>+<kbd>C</kbd> stops at any time and saves everything.

</td>
<td valign="top">

**Rotating proxy server**<br>
`--serve` turns the hits into a local proxy that sends every connection through a different one – with automatic failover when one hangs.

</td>
</tr>
<tr>
<td valign="top">

**Runs everywhere**<br>
macOS, Linux and Windows, Python 3.9 to 3.13. Only two dependencies: `rich` and `certifi`. It even notices when a firewall blocks proxies.

</td>
<td valign="top">

**Thoroughly tested**<br>
450+ tests run offline against real mini proxies and honeypots on `localhost` – on Linux, macOS and Windows with Python 3.9, 3.11 and 3.13.

</td>
</tr>
</table>

<a id="why-not-just-download-a-list"></a>

### Why not just download a list?

| | Typical proxy list repo | **proxy-scraper** |
|---|:---:|:---:|
| Proxies checked right before you use them | ❌ | ✅ |
| Honeypots that fake a successful check filtered out | ❌ | ✅ |
| Proxies that inject scripts or ads filtered out | ❌ | ✅ |
| HTTPS tested with verified TLS | rarely | ✅ |
| Anonymity level and country per proxy | sometimes | ✅ |
| Only proxies that reach *your* target site | ❌ | ✅ `--target` |
| Learns which sources are worth it | ❌ | ✅ |
| Usable as a single rotating proxy | ❌ | ✅ `--serve` |
| Ready-made list without running anything | ✅ | ✅ [live list](#live-list) |

<a id="examples"></a>

## Examples

```bash
# 50 proxies that can do HTTPS – then stop
proxy-scraper --want 50 --https-only

# only Germany, Austria and Switzerland, the 20,000 most promising candidates
proxy-scraper --country DE,AT,CH -l 20000

# fast elite SOCKS5 proxies
proxy-scraper --types socks5 --anonymity elite --max-latency 1500

# 20 proxies that really reach Google AND Discord
proxy-scraper --target google.com --target discord.com --want 20

# only recheck the last hits (plus history) – takes seconds
proxy-scraper --recheck

# wizard with defaults – it keeps what you already passed
proxy-scraper -i --country DE

# which sources deliver the most?
proxy-scraper --list-sources
```

Running from a clone? Replace `proxy-scraper` with `python3 proxy_scraper.py`.

<a id="from-python"></a>

### From Python

```python
from proxyscraper import check_proxies, find_proxies

if __name__ == "__main__":  # needed on macOS/Windows, the parser uses a process pool
    for p in find_proxies(want=20, https=True, countries=["DE", "NL"], no_datacenter=True):
        print(p.url, p.latency, p.country, p.org)

    alive = check_proxies(["socks5://1.2.3.4:1080", "5.6.7.8:3128"])  # your own list
```

Same run as the command line – sources, learning, every check, result files – just without terminal output. Each result has `url`, `latency`, `exit_ip`, `https`, `anonymity`, `country`, `asn`, `org` and `hosting`. There's an async version of both (`find_proxies_async`, `check_proxies_async`).

<a id="proxy-server"></a>

## Rotating proxy server

A list is nice – but usually you just want to enter **one** proxy that always works:

```bash
proxy-scraper --recheck --serve     # recheck the last hits, then go – takes seconds
```

```bash
curl -x http://127.0.0.1:8899 https://api.ipify.org              # a different IP every time
curl -x socks5h://127.0.0.1:8899 https://api.ipify.org           # SOCKS5 on the same port
curl -x http://country-de:x@127.0.0.1:8899 https://api.ipify.org # only German exits
curl -x http://session-cart42:x@127.0.0.1:8899 https://shop.example  # same proxy for this session
curl http://127.0.0.1:8899/__proxy-scraper/status                # pool and counters as JSON
curl http://127.0.0.1:8899/__proxy-scraper/metrics               # the same for Prometheus/Grafana
```

Like commercial rotating proxies, the **username** carries what you want: `country-XX`, `type-http|socks4|socks5` and `session-NAME`, combinable (`country-us-type-socks5-session-a`). It works for HTTP (`Proxy-Authorization`) and SOCKS5 (username/password auth). By default the password is ignored and the server only listens on `127.0.0.1`.

To reach it from other machines, give it a password – every client then has to send it, over HTTP and SOCKS5 alike, and the status page wants it as Basic auth:

```bash
export PROXY_SCRAPER_SERVE_PASSWORD=$(openssl rand -hex 16)   # the env var keeps it out of `ps`
proxy-scraper --recheck --serve --serve-host 0.0.0.0
curl -x "http://country-de:$PROXY_SCRAPER_SERVE_PASSWORD@your-server:8899" https://api.ipify.org
```

Without a password, `--serve-host` means **anyone who reaches the port can use it**. The ready-made [`compose.yaml`](compose.yaml) starts the server in Docker from the live list, with a password, a health check and learned state in a volume: put `PROXY_PASSWORD=…` into `.env`, then `docker compose up -d`.

| Option | What it does |
|---|---|
| `--rotate weighted` | default: fast and proven proxies more often, everyone gets a chance |
| `--rotate random` / `round-robin` | evenly, at random or in turn |
| `--rotate fastest` | always the fastest one that isn't busy |
| `--sticky 300` | the same site keeps its proxy for 5 minutes (logins, carts) |

- every connection goes through a different proxy (unless sticky); fast and proven ones are preferred
- `CONNECT` for HTTPS and plain HTTP requests; HTTP, SOCKS4 and SOCKS5 proxies can sit behind it (SOCKS5 with DNS through the proxy)
- HTTPS only uses proxies that passed the test with **verified TLS** – no broken encryption
- if a proxy stays silent inside the tunnel or returns an error page instead of TLS, the same first packet quietly goes to the next one
- three failures in a row and a proxy leaves the rotation – every 5 minutes those get re-checked and come back if they work again
- `--serve-refill 6` checks fresh proxies every 6 hours in the background (the live list with `--recheck live`, otherwise the last run + history) with the same checks and filters, and adds the hits – a server that runs for days doesn't run dry
- listens on `127.0.0.1` only (unless `--serve-host` says otherwise), optionally with a password; live view with requests, success rate, pool and the latest connections

In testing: 20 of 20 HTTPS requests succeeded, over 15 different exit IPs. In the wizard this is **Proxy server right away**.

<a id="discord-bot"></a>

## Discord bot

The live list can also come to you: [`bot/`](bot/) is a Discord bot that posts every run into a server – a summary with the fastest proxies, the full lists per protocol as files, and slash commands like `/proxies type:socks5 country:DE https:true`. It sets up its own read-only channels when you invite it, and a GitHub Action deploys it to a server as a systemd service. Setup in [bot/README.md](bot/README.md).

<a id="how-it-works"></a>

## How it works

```mermaid
flowchart LR
    A[sources.json<br/>meta lists<br/>GitHub discovery] --> B[Fetch & parse<br/>in parallel on all cores]
    B --> C[Prioritize<br/>history → good sources → rest]
    C --> D[Check<br/>HTTP · SOCKS4 · SOCKS5]
    D --> E[Details<br/>HTTPS · anonymity · country]
    E --> F[results/]
    D -. hit rate per source .-> G[(learned state)]
    G -. next run .-> C
```

1. **Sources** – the curated list in [`sources.json`](proxyscraper/sources.json), meta sources (other projects that maintain lists of proxy sources) and, once a day, a GitHub search for actively maintained repos. Every search adds to what earlier ones found; a list the search hasn't seen for three weeks drops out.
2. **Collect** – plain text, HTML tables, JSON APIs and `type://ip:port` lines are recognized; private and reserved address ranges are dropped. Lists that haven't changed since the last run answer `304` and come from a local cache – a second run right after the first loads 0 MB instead of ~160 MB.
3. **Prioritize** – known working proxies first, then by the learned hit rate of their sources.
4. **Check** – every proxy has to fetch its exit IP from a check target (`checkip.amazonaws.com`, with `ifconfig.me`, `ipinfo.io`, `wtfismyip.com` and `ident.me` as reserves – none of them behind Cloudflare) and return a valid, *foreign* IP. If the target goes down mid-run, the tool switches and re-checks the proxies that were affected, so the statistics don't learn from an outage. Anyone passing your own IP through is out. Then comes the **confirmation** via `httpbin.org`: fake proxies that only answer the first check with “200 + IP” fail here. Finally a static HTML page has to arrive byte for byte as it does without a proxy – anyone injecting ads or scripts is out.
5. **Countries and providers** – looked up offline in the free DB-IP databases, including the provider (ASN) and whether it's probably a datacenter (about 45 % of working proxies are) (downloaded once a month, ~2 µs per lookup); ip-api.com is only asked for the few addresses it doesn't know.
6. **Blocklists** – one DNS lookup per exit IP against SpamCop, cached for the run: about 29 % of working proxies exit from a listed IP, and sites that use the list show those captchas or block them. `--no-blocklisted` drops them. If your DNS resolver is refused by SpamCop (large public resolvers are), the lookup is skipped instead of guessing.
7. **Learn** – hit rates and history are stored. Sources without hits, with content unchanged for a week or permanently unreachable are skipped.

<details>
<summary><b>📸 See the live dashboard and final report</b></summary>
<br>
<div align="center">
<img src="docs/dashboard.svg" alt="Live dashboard while checking" width="860">
<br><br>
<img src="docs/summary.svg" alt="Final report after a run" width="860">
</div>
</details>

<a id="output"></a>

## Output

Every run gets its own folder; `results/latest.txt` always names the newest one (on macOS/Linux there is also the symlink `results/latest`):

```
results/2026-09-24_18-42-07/
├── all.txt        socks5://203.0.113.10:1080   (fastest first)
├── http.txt       203.0.113.20:8080            (plain ip:port lists per type)
├── socks4.txt
├── socks5.txt
├── proxies.json   latency, country, HTTPS, anonymity, exit IP
└── proxies.csv
```

<a id="recipes"></a>

## Recipes

**Use the fastest proxy from the last run** – free proxies die quickly, so `--recheck` first if the run is older than a few minutes

```bash
proxy-scraper --recheck -y
curl -x "$(head -1 results/latest/all.txt)" http://api.ipify.org
```

For HTTPS, pick a proxy with `"https": true` from `proxies.json` – like the Python example below does.

**Python `requests`** (`pip install "requests[socks]"` for SOCKS)

```python
import json
from pathlib import Path

import requests

run = Path("results") / Path("results/latest.txt").read_text().strip()   # works on every OS
proxies = json.loads((run / "proxies.json").read_text())   # fastest first

for p in proxies:
    if not p["https"]:
        continue
    try:
        r = requests.get("https://api.ipify.org", proxies={"http": p["url"], "https": p["url"]}, timeout=8)
        print(p["url"], "→", r.text)
        break
    except requests.RequestException:
        continue  # free proxies come and go – just take the next one
```

**proxychains, Clash / Mihomo** – ready-made configs with `--export`

```bash
proxy-scraper --want 30 -y --export proxychains,clash
proxychains4 -f results/latest/proxychains.conf curl https://api.ipify.org
```

`clash.yaml` has all HTTP and SOCKS5 proxies plus a `url-test` group that always picks the fastest. Both configs leave out HTTP proxies that can't tunnel (`CONNECT`), because these tools tunnel everything.

**In a pipe** – `-o -` prints the hits to stdout, the interface moves to stderr

```bash
proxy-scraper --recheck live --want 20 -y -o - | grep '^socks5://' > socks.txt
```

**Any tool, through the rotating server**

```bash
proxy-scraper --recheck --serve &
export HTTPS_PROXY=http://127.0.0.1:8899 HTTP_PROXY=http://127.0.0.1:8899
pip download requests   # git, pip, npm & co. now go through the pool
```

**Without installing anything** – straight from the live list

```bash
curl -s https://raw.githubusercontent.com/maximilianfeix/proxy-scraper/proxy-list/https.txt | head -5
```

The shell snippets are for macOS and Linux, where `results/latest` points to the newest run. On Windows, `results/latest.txt` holds the folder name instead – in PowerShell:

```powershell
$run = "results\$(Get-Content results\latest.txt)"
curl.exe -x (Get-Content "$run\all.txt" -TotalCount 1) http://api.ipify.org
```

<a id="options"></a>

## Options

<details>
<summary><b>Show all options</b></summary>
<br>

| Option | Description |
|---|---|
| `-i`, `--interactive` | setup wizard (shown automatically without arguments) |
| `-y`, `--yes` | start right away without the wizard |
| `--types http socks5` | only these protocols |
| `-l`, `--limit N` | only check the *N* most promising proxies |
| `--want N` | stop as soon as *N* matching proxies are found |
| `--country DE,AT` | only these countries |
| `--https-only` | only proxies that can tunnel HTTPS |
| `--anonymity elite` | minimum anonymity (`anonymous` or `elite`) |
| `--max-latency MS` | maximum latency |
| `--no-datacenter` | skip proxies whose exit is (probably) in a datacenter – those get blocked sooner |
| `--no-blocklisted` | skip proxies whose exit IP is on the SpamCop blocklist – those often get captchas |
| `--no-dnsbl` | skip the blocklist lookup |
| `--target URL` | only proxies that reach this site (repeatable) |
| `--recheck [FILE\|live]` | only check proxies from a file, the last run, or the public live list |
| `--fast` | skip the HTTPS test (confirmation and anonymity still run) |
| `--no-geo` | skip the country lookup |
| `-c`, `--concurrency N` | simultaneous checks (default: 2000) |
| `-t`, `--timeout S` | timeout per proxy (default: 8 s) |
| `--discover` | search GitHub for new sources right now |
| `--no-cache` | download every list again (unchanged ones are normally skipped via ETag) |
| `--list-sources [N]` | show the source ranking |
| `--serve-host ADDR` | where the proxy server listens (default `127.0.0.1`; `0.0.0.0` for Docker, with a warning) |
| `--serve-password SECRET` | clients must send this password in the proxy login; better set `PROXY_SCRAPER_SERVE_PASSWORD` |
| `--rotate STRATEGY` · `--sticky SEC` | how the proxy server picks proxies, see [above](#proxy-server) |
| `--serve-refill HOURS` | while serving, check fresh proxies every HOURS and add the hits to the pool |
| `--serve [PORT]` | afterwards serve as a rotating proxy on `127.0.0.1:PORT` (default: 8899) |
| `-o FILE` | also write all hits to this file; `-o -` prints them to stdout |
| `--export FORMATS` | extra files for other tools: `proxychains`, `clash`, `curl` or `all` |
| `-V`, `--version` | print the version |
| `--completion SHELL` | print the tab completion script for bash, zsh or fish |

Everything else: `proxy-scraper --help`

</details>

> [!TIP]
> For the GitHub search a logged-in [`gh`](https://cli.github.com/) or the `GITHUB_TOKEN` environment variable is enough. Without a token the API limit is 60 requests per hour, and only 40 repos are searched.

<a id="github-actions"></a>

## GitHub Actions

The repo does part of the work itself:

| Workflow | What it does |
|---|---|
| [**tests**](../../actions/workflows/tests.yml) | 3 operating systems × 3 Python versions, plus a built and installed package – on every push and pull request |
| [**lint**](../../actions/workflows/lint.yml) | `ruff` with a pinned version – same rules locally and in CI |
| [**codeql**](../../actions/workflows/codeql.yml) | security analysis on every push and once a week |
| [**proxy list**](../../actions/workflows/proxy-list.yml) | every hour: collect, check, publish to `proxy-list`. The learned statistics live in the Actions cache, so the tool keeps getting better in the cloud too |
| [**docker**](../../actions/workflows/docker.yml) | builds the image on every change and runs a real scan inside it; on a version tag it publishes `linux/amd64` + `linux/arm64` to `ghcr.io` |
| [**release**](../../actions/workflows/release.yml) | on a version tag: test, build, smoke-test and publish a GitHub release with the wheel |
| [**discord bot**](../../actions/workflows/bot.yml) | tests the bot and deploys it to the server on every change in `bot/` |
| **Dependabot** | keeps the action versions up to date |

<a id="faq"></a>

## FAQ

<details>
<summary><b>Almost nothing gets through.</b></summary>
<br>

Many company, school and university networks block proxy connections. The tool notices a hit rate below 0.2 % and warns you – a different network such as a phone hotspot helps. The learned statistics are not downgraded in such a run.

</details>

<details>
<summary><b>Does it work on Windows?</b></summary>
<br>

Yes, in PowerShell and Windows Terminal. `uvloop` doesn't exist there and is skipped automatically. In the old `cmd.exe` window some symbols may be missing depending on the font.

</details>

<details>
<summary><b>Why does it find fewer proxies than other lists claim to have?</b></summary>
<br>

Because only proxies that pass every check are kept. Many lists count anything that accepts a TCP connection; here a proxy must fetch two independent pages and show a foreign IP. That's usually a few hundred out of a million candidates – but they work.

</details>

<details>
<summary><b>What about proxies with a username and password?</b></summary>
<br>

Lines like `socks5://user:pass@1.2.3.4:1080` keep their login: HTTP proxies get a `Proxy-Authorization` header, SOCKS5 uses username/password auth (RFC 1929), SOCKS4 the user ID. The same works for `--recheck` with your own list. The result files keep the credentials, the terminal only shows `user:•••`.

</details>

<details>
<summary><b>How fresh is the live list?</b></summary>
<br>

It's rebuilt every hour; the “updated” badge shows the last run. Free proxies come and go quickly, so for anything important run `proxy-scraper --recheck` right before use.

</details>

<details>
<summary><b>Is it safe to use free proxies?</b></summary>
<br>

Only for things that don't matter. Public proxies are run by strangers who can read everything that isn't encrypted. Never send passwords or personal data through them, and only use them for legal purposes.

</details>

<a id="roadmap"></a>

## Roadmap

What's next is tracked in the milestone [**v1.7**](../../milestone/7) – ideas and wishes are welcome as an [issue](../../issues/new/choose). During Hacktoberfest there are [beginner-friendly issues](../../issues?q=is%3Aopen+label%3Ahacktoberfest) with pointers on where to start.

- [ ] [Publish on PyPI](../../issues/42) so it's just `pipx install proxy-scraper`
- [ ] [Protocol detection on the same connection](../../issues/44)
- [ ] [sing-box export](../../issues/113), [PowerShell completion](../../issues/114), [shareable filters on the website](../../issues/116)

Shipped in [v1.6](../../milestone/6): spam blocklist check for every exit IP, a live list refreshed every hour, pages per protocol and country, an optional password for the proxy server and a pool that refills itself while it runs, `compose.yaml`, `-o -` for pipes, a Discord bot, and a new website and README – everything in English now.

Shipped in [v1.5](../../milestone/5): content tampering check, live list website with trend and stable proxies, provider/datacenter info, a much bigger proxy server (rotation strategies, sticky sessions, SOCKS5 inbound, status and Prometheus metrics), `--recheck live`, Python API, shell completion. Measured and dropped earlier: protocol detection with an extra connection ([#3](../../issues/3)) and IPv6 ([#1](../../issues/1)).

<a id="contributing"></a>

## Contributing

Bug reports, new sources and pull requests are very welcome – see [CONTRIBUTING.md](CONTRIBUTING.md), and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for how the pieces fit together. The short version:

```bash
pip install -e ".[dev]"
python3 -m pytest          # runs offline – fake proxies on localhost
ruff check .
python3 docs/make_demo.py  # regenerate the images in this README
```

<details>
<summary><b>Project structure</b></summary>

```
proxy_scraper.py        entry point when run from a clone
bot/                    Discord bot for the live list (own requirements, deployed by GitHub Actions)
proxyscraper/
├── cli.py              arguments, wizard or direct start
├── app.py              one run in phases: network → jobs → check → learn & report
├── options.py          RunOptions + Filters – all settings in one place
├── pipeline.py         collect sources, prioritize, check loop
├── checker.py          checks, honeypot confirmation, HTTPS test
├── handshake.py        HTTP/SOCKS4/SOCKS5 handshakes incl. login
├── judges.py           check targets, Cloudflare filter, failover
├── sources.py          source lists, meta sources, GitHub discovery, statistics
├── sources.json        curated sources
├── fetchcache.py       ETag cache for unchanged lists
├── parsing.py          find proxies in text, HTML and JSON
├── history.py          history of working proxies
├── geo.py              countries: offline first, ip-api.com as fallback
├── asndb.py            DB-IP provider database, datacenter heuristic
├── geodb.py            DB-IP country database (monthly, binary search)
├── targets.py          target sites for --target
├── output.py           result files
├── exporters.py        proxychains, Clash and curl formats (--export)
├── server/             rotating proxy server (--serve): pool · http · upstream · socks · status · core
├── api.py              find_proxies() / check_proxies() for Python
├── publish.py          live list for GitHub Actions
├── paths.py            where state and results are stored
├── compat.py           differences between Unix and Windows
├── netio.py            small HTTP client on asyncio
└── ui/                 widgets · dashboard · report · wizard · serve · keys
```

</details>

<a id="acknowledgements"></a>

## Acknowledgements

proxy-scraper stands on the work of the people who publish free proxy lists. Thanks to everyone listed in [`sources.json`](proxyscraper/sources.json), and especially to

- [monosans/proxy-scraper-checker](https://github.com/monosans/proxy-scraper-checker) and [gfpcom/free-proxy-list](https://github.com/gfpcom/free-proxy-list), whose curated source collections are read as meta sources
- [Textualize/rich](https://github.com/Textualize/rich), which draws the whole terminal UI
- [IP Geolocation by DB-IP](https://db-ip.com) – the free country database (CC BY 4.0) used for offline country lookups
- [httpbin](https://httpbin.org), [checkip.amazonaws.com](https://checkip.amazonaws.com), [ifconfig.me](https://ifconfig.me), [ipinfo.io](https://ipinfo.io), [wtfismyip.com](https://wtfismyip.com), [ident.me](https://ident.me) and [ip-api.com](https://ip-api.com), used as check targets and for country lookups

## Disclaimer

This tool only collects publicly listed proxies and checks whether they work. You are responsible for how you use them – respect the terms of the sites you visit and the laws where you live.

<div align="center">

---

<sub>Made in Germany by <a href="https://github.com/maximilianfeix">@maximilianfeix</a> · <a href="LICENSE">MIT License</a> · <a href="CHANGELOG.md">Changelog</a> · <a href="SECURITY.md">Security</a> · <a href="CONTRIBUTING.md">Contributing</a></sub>

<sub>If proxy-scraper saves you time, a ⭐ helps others find it.</sub>

</div>
