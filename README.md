<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/banner-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="docs/banner-light.svg">
  <img src="docs/banner-dark.svg" alt="proxy-scraper – free proxies that actually work" width="100%">
</picture>

[![tests](https://github.com/maximilianfeix/proxy-scraper/actions/workflows/tests.yml/badge.svg)](https://github.com/maximilianfeix/proxy-scraper/actions/workflows/tests.yml)
[![Release](https://img.shields.io/github/v/release/maximilianfeix/proxy-scraper?style=flat-square&color=D4F77A&labelColor=121113)](https://github.com/maximilianfeix/proxy-scraper/releases/latest)
[![Live proxies](https://img.shields.io/endpoint?url=https%3A%2F%2Fraw.githubusercontent.com%2Fmaximilianfeix%2Fproxy-scraper%2Fproxy-list%2Fbadges%2Ftotal.json&style=flat-square&labelColor=121113)](#live-list)
[![PyPI](https://img.shields.io/pypi/v/proxy-scraper-cli?style=flat-square&color=D4F77A&labelColor=121113&label=pypi)](https://pypi.org/project/proxy-scraper-cli/)
[![Downloads](https://img.shields.io/pepy/dt/proxy-scraper-cli?style=flat-square&color=D4F77A&labelColor=121113&label=downloads)](https://pepy.tech/projects/proxy-scraper-cli)
[![Python](https://img.shields.io/badge/python-3.9–3.14-D4F77A?style=flat-square&labelColor=121113)](pyproject.toml)
[![Stars](https://img.shields.io/github/stars/maximilianfeix/proxy-scraper?style=flat-square&color=D4F77A&labelColor=121113)](https://github.com/maximilianfeix/proxy-scraper/stargazers)
[![License](https://img.shields.io/badge/license-MIT-D4F77A?style=flat-square&labelColor=121113)](LICENSE)

<a href="https://proxy-scraper.de/"><img src="https://img.shields.io/badge/Browse_the_live_list-D4F77A?style=for-the-badge&labelColor=121113" alt="Browse the live list"></a>
<a href="https://github.com/maximilianfeix/free-proxy-list"><img src="https://img.shields.io/badge/Just_the_lists-121113?style=for-the-badge" alt="Just the lists: free-proxy-list"></a>
<a href="#install"><img src="https://img.shields.io/badge/Install-121113?style=for-the-badge" alt="Install"></a>
<a href="#from-python"><img src="https://img.shields.io/badge/Python_API-121113?style=for-the-badge" alt="Python API"></a>
<a href="#mcp"><img src="https://img.shields.io/badge/MCP_server-121113?style=for-the-badge" alt="MCP server for AI agents"></a>
<a href="bot/"><img src="https://img.shields.io/badge/Discord_bot-121113?style=for-the-badge" alt="Discord bot"></a>

**English** · [简体中文](README.zh-CN.md) · [Español](README.es.md) · [Deutsch](README.de.md) · [Русский](README.ru.md) · [Português (Brasil)](README.pt-BR.md) · [Français](README.fr.md)

[Install](#install) · [Live list](#live-list) · [Check states](#check-states) · [For AI agents](#mcp) · [Proxy server](#proxy-server) · [Recipes](docs/recipes.md) · [Options](docs/options.md) · [FAQ](docs/faq.md) · [All docs](docs/README.md)

</div>

---

**Proxy checks you can inspect: what passed, what failed, and when.** proxy-scraper collects public HTTP, SOCKS4 and SOCKS5 proxies from hundreds of lists, runs up to four checks on each one and keeps the outcome of each check for the proxies it lists (for the rest it counts how each check ended), so "working" is something you can look at instead of a label you have to trust.

https://github.com/user-attachments/assets/b99c1d8f-5bce-4a52-a8a9-b9c2c726301b

<sub>21 seconds · real interface, example numbers, documentation IPs · <a href="docs/video/proxy-scraper.mp4">mp4</a></sub>

**Try it** – no install needed, `uvx` comes with [uv](https://docs.astral.sh/uv/) (`pipx run` does the same):

```bash
uvx proxy-scraper-cli --pick 3 --verify               # up to 3 proxies from the hourly list that pass right now, from your network
uvx proxy-scraper-cli --diagnose socks5://HOST:PORT   # one proxy, check by check: what it did and what it didn't
```

<div align="center">
<img src="docs/demo/checks.gif" alt="Terminal recording: proxy-scraper --pick 2 --verify --https-only prints two proxies and says on stderr why the other four were left out; proxy-scraper --diagnose shows each check of one proxy with its result" width="880">
</div>

<sub>A real terminal recording, made against six simulated proxies on localhost ([reproduce it](docs/demo/)). It shows how results are reported. It measures nothing about public proxies.</sub>

The package is `proxy-scraper-cli` on PyPI (the plain name is taken). Once [installed](#install), the command is `proxy-scraper`. `--verify` and `--diagnose` need version 1.30 or newer.

**Three ways to get proxies, and what "checked" means for each:**

| Command | Where the proxies come from | Checked | Takes |
|---|---|---|---|
| `proxy-scraper --pick 5` | the [published list](#live-list) | from GitHub's servers when the list was built, about every hour | under a second |
| `proxy-scraper --pick 5 --verify` | the published list | **now, from your network** | seconds to a minute and a half at most |
| `proxy-scraper -y` | every list the tool knows | now, from your network | minutes (about three in the hourly runs) |

**What you get**

- **Every check has an outcome you can read.** `passed`, `failed`, `unavailable` or `skipped`, with a reason code, the target and the time, in the terminal, in JSON and from Python. A check that didn't run is never shown as passed, and a check target that is down doesn't turn the proxies checked against it into failures. → [Check states](docs/check-states.md)
- **Fresh when it matters.** `--pick --verify` checks a few proxies from your own network, usually in seconds. `--recheck` does the same for [a list of your own](#examples), and `--diagnose` tells you why one proxy doesn't work.
- **More than a list.** A [rotating local proxy server](#proxy-server), a [Python API](#from-python), an [MCP server](#mcp) for AI agents, Docker, and exports for curl, proxychains, Clash and sing-box.

**What it can't do.** Free proxies are run by strangers, and of one hour's list only about a quarter is on the list again a day later. A pass is one measurement, from one network, against test targets: it is not a promise for the next hour or for the site you care about. The HTTPS check is a verified TLS connection to one test host, not a security rating. Use free proxies for public data and testing, never for logins, payments or anything personal. → [What the numbers show and what they don't](docs/free-proxies-in-numbers.md) · [Why free proxies fail](docs/why-free-proxies-fail.md) · [How it compares](docs/comparison.md) · [Who runs free proxies](docs/faq.md#who-runs-free-proxies)

**Only want the lists?** You don't need this tool: [free-proxy-list](https://github.com/maximilianfeix/free-proxy-list) has them as plain files per protocol and country, rebuilt about every hour. Or straight from here: [all.txt](https://proxy-scraper.de/all.txt) · [http.txt](https://proxy-scraper.de/http.txt) · [socks4.txt](https://proxy-scraper.de/socks4.txt) · [socks5.txt](https://proxy-scraper.de/socks5.txt) · [proxies.json](https://proxy-scraper.de/proxies.json) · [more formats](#live-list)

**Used by:** the hourly list is a built-in source of [monosans/proxy-scraper-checker](https://github.com/monosans/proxy-scraper-checker) and [gfpcom/free-proxy-list](https://github.com/gfpcom/free-proxy-list).

<a id="install"></a>

## Install

**With [pipx](https://pipx.pypa.io/)** (recommended – gives you a `proxy-scraper` command in its own environment):

```bash
pipx install proxy-scraper-cli
proxy-scraper
```

**With [Homebrew](https://brew.sh)** on macOS and Linux:

```bash
brew install maximilianfeix/tap/proxy-scraper
```

The formula follows each release within about a day.

Docker, pip, a faster event loop, the latest main, tab completion and where state and results are stored: [every other way to install](docs/install.md).

Started without arguments, a wizard asks what you are looking for – a preset (find everything, browsing, maximum anonymity, fast, a few right now, recheck, proxy server right away, …) or step by step: [the wizard and its presets](docs/options.md#wizard-presets).

Keys: <kbd>↑</kbd><kbd>↓</kbd> select · <kbd>Space</kbd> toggle · <kbd>1</kbd>–<kbd>9</kbd> jump · <kbd>Enter</kbd> next · <kbd>Esc</kbd> back · <kbd>q</kbd> quit. In scripts and cron jobs the wizard never shows up – pass options or `-y`.

<a id="live-list"></a>

## Live proxy list

Don't want to scan yourself? About every hour **GitHub Actions** runs the tool and publishes the hits to the [`proxy-list`](../../tree/proxy-list) branch – every entry passed the first request, the second request and the content check in the last run (the HTTPS test is recorded per entry, not required), best first: fast ones that are likely to still be up come on top.

> **Just want the lists?** They also live in a repository of their own, **[maximilianfeix/free-proxy-list](https://github.com/maximilianfeix/free-proxy-list)** – one list per protocol, per country and per site, updated every hour, with the numbers of the last run on the front page. Watch or star it to keep it at hand. Other tools pull it too: [monosans/proxy-scraper-checker](https://github.com/monosans/proxy-scraper-checker) and [gfpcom/free-proxy-list](https://github.com/gfpcom/free-proxy-list) use it as a built-in source.

<a href="https://proxy-scraper.de/"><picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://proxy-scraper.de/chart-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="https://proxy-scraper.de/chart-light.svg">
  <img src="https://proxy-scraper.de/chart-dark.svg" alt="Working proxies over the last days, stacked by protocol – redrawn with every run" width="100%">
</picture></a>

**→ [Browse it on the website](https://proxy-scraper.de/)** – search, filter by type, country, HTTPS, provider and latency, see how long each proxy has been on the list and in how many of the week's runs, copy or download exactly the proxies you need.

Every protocol and country also has its own page with a plain download, e.g. [SOCKS5](https://proxy-scraper.de/socks5/) or [Germany](https://proxy-scraper.de/country/de/) (`country/de/proxies.txt`).

<div align="center"><a href="https://proxy-scraper.de/"><img src="docs/website.png" alt="The live list website" width="860"></a></div>

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
| Gets through to Google · Reddit · Amazon · Instagram · TikTok · Discord (one test request got a normal page in the last run) | `type://ip:port` | [google.txt](https://raw.githubusercontent.com/maximilianfeix/proxy-scraper/proxy-list/works-with/google.txt) · [reddit.txt](https://raw.githubusercontent.com/maximilianfeix/proxy-scraper/proxy-list/works-with/reddit.txt) · [amazon.txt](https://raw.githubusercontent.com/maximilianfeix/proxy-scraper/proxy-list/works-with/amazon.txt) · [instagram.txt](https://raw.githubusercontent.com/maximilianfeix/proxy-scraper/proxy-list/works-with/instagram.txt) · [tiktok.txt](https://raw.githubusercontent.com/maximilianfeix/proxy-scraper/proxy-list/works-with/tiktok.txt) · [discord.txt](https://raw.githubusercontent.com/maximilianfeix/proxy-scraper/proxy-list/works-with/discord.txt) |
| Stable, on the list in 90 %+ of this week's runs | `type://ip:port` | [stable.txt](https://raw.githubusercontent.com/maximilianfeix/proxy-scraper/proxy-list/stable.txt) |
| With all details | latency, country, HTTPS, anonymity, exit IP, uptime, sites | [proxies.json](https://raw.githubusercontent.com/maximilianfeix/proxy-scraper/proxy-list/proxies.json) · [proxies.csv](https://raw.githubusercontent.com/maximilianfeix/proxy-scraper/proxy-list/proxies.csv) |

<a href="https://proxy-scraper.de/"><picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://proxy-scraper.de/countries-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="https://proxy-scraper.de/countries-light.svg">
  <img src="https://proxy-scraper.de/countries-dark.svg" alt="Countries with the most working proxies right now" width="100%">
</picture></a>

```bash
curl -s https://raw.githubusercontent.com/maximilianfeix/proxy-scraper/proxy-list/socks5.txt | head
```

**Where they come from:** [which free proxy lists actually work](https://proxy-scraper.de/sources/) ranks every source of the hourly runs – how many proxies each one lists, how many passed every check and the share. The same as data: [sources.json](https://proxy-scraper.de/sources.json).

**Over time:** every day the first run's `proxies.json` is kept for good as a gzipped asset of the release of that year, like [snapshots-2026](../../releases/tag/snapshots-2026) – `proxies-2026-09-28.json.gz` and so on, for anyone who wants to look at free proxies over weeks and months.

Every file is also on GitHub Pages, which sits behind a CDN, isn't rate limited like raw.githubusercontent and sends CORS headers, so it works straight from the browser: `https://proxy-scraper.de/socks5.txt`. [jsDelivr](https://cdn.jsdelivr.net/gh/maximilianfeix/proxy-scraper@proxy-list/) works too, but can lag behind by a few hours.

Or let the tool start from it: `proxy-scraper --recheck live` downloads the list and checks it again from **your** network – well under a minute instead of a full scan. How many still work from your network differs a lot from the list's own count, which is the point of checking again. Add `--serve` and the result is a rotating proxy.

<a id="check-states"></a>

## Check states

Every check of a proxy ends in one of four states. They are in `proxies.json`, in the CSV, in `--pick --json`, in `--diagnose`, in the Python API (`result.checks`) and in the MCP results.

| State | Meaning |
|---|---|
| `passed` | The check ran and the proxy did what was asked. |
| `failed` | The check ran, its target was fine, and the proxy did not do what was asked. |
| `unavailable` | The check could not run, or says nothing about the proxy: its target didn't answer directly either, there was no reference to compare with, or this machine ran out of sockets. |
| `skipped` | Left out on purpose: `--fast`, a filter had already ruled the proxy out, or an earlier check failed. |

Two rules follow from that:

- **A check that didn't run is never `passed`.** Before 1.30, a run without a reachable second target kept every proxy as if it had been confirmed, and a missing reference page looked like "content unchanged".
- **A check target that is down doesn't fail the proxies checked against it.** When a second request, a content request that returned a different page, or an HTTPS test fails, the tool asks the target directly: at most once every 3 seconds however many proxies fail in between, and a "down" answer is reused for 10 seconds. If the target doesn't answer, the proxy's check is `unavailable`, not `failed`. For the first request a scan does it differently: it watches the target, switches to another one and checks the affected proxies again. `--diagnose` and `--pick --verify` have no such watcher and ask directly, as for the later checks. Two things are never asked about, because the target did answer: a second site that saw a different exit IP, and a proxy that could not be connected to in the first place.

The checks, what each `passed` does and doesn't mean, the fields and every reason code: [docs/check-states.md](docs/check-states.md).

<a id="mcp"></a>

## For AI agents (MCP)

<!-- mcp-name: io.github.maximilianfeix/proxy-scraper -->

`proxy-scraper-mcp` is an [MCP](https://modelcontextprotocol.io) server: Claude Code, Claude Desktop, Cursor, VS Code, Codex and any other MCP client can ask for working proxies and load pages through them.

[![proxy-scraper MCP server on Glama](https://glama.ai/mcp/servers/maximilianfeix/proxy-scraper/badges/score.svg)](https://glama.ai/mcp/servers/maximilianfeix/proxy-scraper)

| Tool | What it does |
|---|---|
| `get_proxies` | proxies from the hourly list, as checked in its last run – filter by protocol, country, HTTPS, elite, no datacenter, not blocklisted, stable, uptime, latency, gets through to Google/Reddit/Amazon |
| `check_proxies` | checks proxies from your own network, so they work from where your code runs (30–90 s, reports progress) |
| `fetch_url` | loads a page through a proxy from the checked list, switches proxies by itself when one fails, returns readable text – HTTPS only through proxies that passed the TLS test |

Things to ask your agent: *"Load bbc.com/news as seen from the UK"*, *"Give me 5 SOCKS5 proxies from Germany that aren't in a datacenter"*, *"Check which of these sites block free proxies"*.

Needs [uv](https://docs.astral.sh/uv/) – it fetches a suitable Python by itself if yours is older than 3.10. **Claude Code:**

```bash
claude mcp add proxy-scraper -- uvx --python ">=3.10" --from "proxy-scraper-cli[mcp]" proxy-scraper-mcp
```

**Claude Desktop, Cursor and most other clients** – add this to the MCP config (Claude Desktop: Settings → Developer → Edit Config, Cursor: `~/.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "proxy-scraper": {
      "command": "uvx",
      "args": ["--python", ">=3.10", "--from", "proxy-scraper-cli[mcp]", "proxy-scraper-mcp"]
    }
  }
}
```

**VS Code, Codex, Docker, or without uv:** [setup for every other client](docs/mcp.md). It's also in the [official MCP registry](https://registry.modelcontextprotocol.io) as `io.github.maximilianfeix/proxy-scraper`, so clients that browse the registry can install it from there.

The server tells agents what it tells you: free proxies are run by strangers, so no logins, cookies or personal data through them. Local and private addresses are refused, and results go to proxy-scraper's data folder, not into the project you're working in.

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

Don't need a fresh scan? `live_proxies` takes the [live list](#live-list) instead – no checks, one download, done in about a second:

```python
import itertools, requests
from proxyscraper import live_proxies

proxies = live_proxies(types=["socks5"], https=True, min_uptime=90)  # the reliable ones this week
pool = itertools.cycle(p.url for p in proxies)
r = requests.get("https://api.ipify.org", proxies={"https": next(pool)}, timeout=15)  # pip install "requests[socks]"
```

Same filters as `find_proxies`, plus `min_uptime`, `works_on` (`["google"]`, `"reddit"`, `"amazon"`, `"instagram"`, `"tiktok"`, `"discord"`) and `limit`. Every result also has `uptime_24h`, `uptime_7d`, `first_seen`, `up_for_hours` and `sites`.

Or let the library do the retrying: `ProxyRotator` loads a URL through the list and moves on to the next proxy when one fails, and `proxy_url()` gives requests, httpx, Playwright or Scrapy one local address that rotates behind the scenes – [Python API: rotating through the list](docs/python.md).

<a id="proxy-server"></a>

## Rotating proxy server

A list is nice – but usually you just want to enter **one** proxy address and have something behind it that keeps trying:

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

Without a password the server refuses to start on any address but `127.0.0.1`: that would be an open proxy for **anyone who reaches the port** (Docker publishes ports past host firewalls like ufw). If a firewall or `-p 127.0.0.1:…` already keeps others out, say so with `--serve-open`. The ready-made [`compose.yaml`](compose.yaml) starts the server in Docker from the live list, with a password, a health check and learned state in a volume: put `PROXY_PASSWORD=…` into `.env`, then `docker compose up -d`.

Rotation strategies, sticky sessions, failover, background refill and the live dashboard: [docs/proxy-server.md](docs/proxy-server.md).

<a id="pool-api"></a>

### Proxy pool API

Some programs want a proxy *address*, not a proxy – to hand it to a browser, a worker or a queue. The same port answers plain HTTP requests with one:

```bash
curl http://127.0.0.1:8899/get                          # one proxy as JSON, chosen like a connection would be
curl "http://127.0.0.1:8899/get?country=DE&https=1&format=txt"   # → http://203.0.113.7:8080
curl "http://127.0.0.1:8899/all?protocol=socks5&limit=20"        # the 20 best SOCKS5 proxies
curl "http://127.0.0.1:8899/report?proxy=203.0.113.7:8080&ok=0"  # it failed you – three times and it's out
```

All endpoints, filters and what's compatible with jhao104/proxy_pool: [Proxy pool API](docs/proxy-server.md#pool-api).

<a id="discord-bot"></a>

## Discord and Telegram bot

The live list can also come to you: [`bot/`](bot/) is a Discord bot that posts every run into a server – a summary with the fastest proxies, the full lists per protocol as files, and slash commands like `/proxies type:socks5 country:DE https:true`. It sets up its own read-only channels when you invite it, and a GitHub Action deploys it to a server as a systemd service. The same process answers on Telegram too: `/proxy de socks5` for one proxy with a curl line, `/proxies 10 us https` for a short list. Setup in [bot/README.md](bot/README.md).

<a id="docs"></a>

## Documentation

Everything that used to be further down this README now has its own page – [all docs](docs/README.md):

<a id="features"></a>

### Features

What the tool does, check by check and feature by feature: [How it works → Features](docs/how-it-works.md#features).

<a id="why-not-just-download-a-list"></a>

### Why not just download a list?

A list tells you what worked for its author when it was built. What the tool adds: [How it works → Why not just download a list?](docs/how-it-works.md#why-not-just-download-a-list) · [how it compares](docs/comparison.md).

<a id="how-it-works"></a>

### How it works

Sources, collecting, prioritizing, the checks, countries and providers, blocklists, learning: [docs/how-it-works.md](docs/how-it-works.md). Your own lists with `--source`: [recipes](docs/recipes.md#your-own-lists).

<a id="output"></a>

### Output

Every run gets its own folder; `results/latest.txt` always names the newest one – the layout is in [docs/options.md](docs/options.md#output).

<a id="recipes"></a>

### Recipes

requests, httpx, aiohttp, Scrapy, Selenium, proxychains, Clash / Mihomo, sing-box, PAC, Proxifier, Burp Suite / ZAP / mitmproxy, pipes, a GitHub workflow, Windows: [docs/recipes.md](docs/recipes.md).

<a id="options"></a>

### Options

Every option in one table: [docs/options.md](docs/options.md). Everything else: `proxy-scraper --help`

<a id="github-actions"></a>

### GitHub Actions

The workflows that test, lint, build the hourly list and release: [docs/how-it-works.md](docs/how-it-works.md#github-actions). To use proxies in your own workflow: [the GitHub Action](docs/github-action.md).

<a id="faq"></a>

### FAQ

[Who runs free proxies – and should you use them?](docs/faq.md#who-runs-free-proxies) · almost nothing gets through · Windows · fewer proxies than other lists · logins · how fresh the list is · is it safe: [docs/faq.md](docs/faq.md).

<a id="who-runs-free-proxies"></a>

<a id="roadmap"></a>

### Roadmap

What's next is in the [open issues](../../issues) – ideas and wishes are welcome as an [issue](../../issues/new/choose). During Hacktoberfest there are [beginner-friendly issues](../../issues?q=is%3Aopen+label%3Ahacktoberfest) with pointers on where to start. What shipped in each version: [docs/roadmap.md](docs/roadmap.md).

<a id="contributing"></a>

## Contributing

Bug reports, new sources and pull requests are very welcome – see [CONTRIBUTING.md](CONTRIBUTING.md), and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for how the pieces fit together. The short version:

```bash
pip install -e ".[dev]"
python3 -m pytest          # runs offline – fake proxies on localhost
ruff check .
python3 docs/make_demo.py  # regenerate the images in this README
```

The project structure, file by file, is in [How it works](docs/how-it-works.md#project-structure).

<a id="community"></a>

## Community

Questions, ideas and things you built with it go to [Discussions](https://github.com/maximilianfeix/proxy-scraper/discussions) – bugs to the [issues](../../issues). If proxy-scraper saves you time, a ⭐ helps others find it.

Thanks to everyone who helped build it – new sources, countries, Python 3.14, examples and more:

<a href="https://github.com/maximilianfeix/proxy-scraper/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=maximilianfeix/proxy-scraper" alt="Contributors to proxy-scraper">
</a>

Want to join? [Beginner-friendly issues](../../issues?q=is%3Aopen+label%3A%22good+first+issue%22) say where to start.

From the same author: [dejabuilt](https://github.com/maximilianfeix/dejabuilt), an agent skill that checks GitHub before you build – it tells you whether a project idea already exists, with the numbers.

<a href="https://star-history.com/#maximilianfeix/proxy-scraper&Date">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=maximilianfeix/proxy-scraper&type=Date&theme=dark">
    <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=maximilianfeix/proxy-scraper&type=Date">
    <img alt="Star history of proxy-scraper" src="https://api.star-history.com/svg?repos=maximilianfeix/proxy-scraper&type=Date" width="600">
  </picture>
</a>

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
