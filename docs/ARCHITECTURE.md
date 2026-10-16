# Architecture

How proxy-scraper is put together, and why some things are the way they are. If you want to change something, this is the map.

## The big picture

A run has four phases. `app.py` drives them, everything else is a module that does one job.

```mermaid
flowchart LR
    subgraph prepare["1 · Prepare"]
        J[judges.py<br/>pick check target] --> N[own IP · confirm target<br/>tamper reference]
    end
    subgraph collect["2 · Collect"]
        S[sources.py<br/>curated · meta · GitHub] --> F[fetchcache.py<br/>ETag / 304]
        F --> P[parsing.py<br/>text · HTML · JSON]
    end
    subgraph check["3 · Check"]
        Q[pipeline.py<br/>priority queue] --> C[checker.py<br/>handshake · confirm · tamper · HTTPS]
        C --> G[geo.py · asndb.py · blocklist.py<br/>country · provider · blocklist]
    end
    subgraph finish["4 · Learn & report"]
        O[output.py · exporters.py] --> L[sources · history<br/>learned stats]
    end
    prepare --> collect --> check --> finish
    finish -. optional .-> SV[server/<br/>rotating proxy]
```

## Modules

| Module | Job |
|---|---|
| `cli.py` | arguments, wizard or direct start |
| `options.py` | `RunOptions` and `Filters` – every setting in one object, round-trips to argv |
| `app.py` | one run in phases, the only place that knows the order of things |
| `sources.py` | source lists, meta sources, GitHub discovery, per-source hit statistics |
| `fetchcache.py` | conditional downloads; parsed keys of unchanged lists come from `data/fetch-cache` |
| `parsing.py` | finds proxies in any format, drops private/reserved ranges, keys are `"type ip:port"` strings |
| `pipeline.py` | collect in parallel (process pool for big lists), prioritise, run the check workers |
| `checker.py` | the checks themselves, see below |
| `checkstate.py` | the outcome of a check: four states, reason codes, what goes into JSON |
| `verify.py` | checking a handful of proxies with every outcome kept: `--pick --verify` (bounded attempts, a few at a time, a time limit) and `--diagnose` |
| `handshake.py` | HTTP/SOCKS4/SOCKS5 handshakes including login, shared by checker and server |
| `judges.py` | check targets, Cloudflare filter, failover while running |
| `geo.py` · `geodb.py` · `asndb.py` | countries and providers, offline from DB-IP, ip-api.com as fallback |
| `blocklist.py` | is the exit IP on SpamCop? One cached DNS lookup per IP, skipped when the resolver is refused |
| `targets.py` | target sites for `--target` |
| `completion.py` | bash/zsh/fish/PowerShell completion, generated from the argparse parser so it can't go stale |
| `history.py` | which proxies worked before – they are checked first next time |
| `output.py` · `exporters.py` · `publish.py` · `mirror.py` | result files, proxychains/Clash/sing-box/curl configs, the live list and its website, and the lists alone in the free-proxy-list repo |
| `sites.py` · `speed.py` · `runsteps.py` | extra steps on a finished run in the hourly workflow: which big sites let each proxy through, how fast it downloads. `runsteps.py` is what they share – loading and atomically saving the run's rows, the HTTPS-capable ones, a limit on parallel probes, verified TLS tunnels |
| `pages.py` · `proxypages.py` · `sourcepages.py` · `charts.py` · `report.py` | what the live list publishes besides the data: a page per protocol and country, a page per proxy with its week of checks, the ranking of the sources, the SVG charts in the README, the weekly report with its feed |
| `action.py` | the GitHub Action (`action.yml` in the root): picks proxies from the live list for a workflow |
| `site/` | the live list website (one static `index.html` plus images), published next to the JSON files |
| `server/` | the rotating proxy server (`--serve`) |
| `agent.py` · `mcp_server.py` · `mcp_entry.py` | the MCP server for AI agents: `agent.py` has the logic and runs without the MCP SDK (so it's tested on 3.9 too), `mcp_server.py` describes it as tools, `mcp_entry.py` is the `proxy-scraper-mcp` command. stdout carries the protocol, everything else goes to stderr |
| `api.py` | `find_proxies()` / `check_proxies()` / `live_proxies()` for use from Python |
| `ui/` | everything that draws: widgets, dashboard, report, wizard, server view |

`ui/` only draws. It never decides anything, and during a run nothing outside `ui/` prints directly – all output goes through `widgets.console`, which is also how the tests and the Python API silence it. (`publish.py` and `mirror.py` are the exception: they run in GitHub Actions and just print status lines.)

## What happens to one proxy

```mermaid
flowchart TD
    A[key: socks5 1.2.3.4:1080] --> B{address known<br/>to be unreachable?}
    B -- yes --> X[skip]
    B -- no --> C[handshake + GET check target<br/>exit IP must be public and not ours]
    C -- fails --> X
    C --> D[confirm via httpbin.org<br/>same exit IP · anonymity from headers]
    D -- fails, target answers directly --> H[failed second request<br/>dropped]
    D -- fails, target down too --> U[confirm: unavailable<br/>kept, and says so]
    D --> E[fetch a static page<br/>must match byte for byte]
    U --> E
    E -- differs --> T[content mismatch<br/>dropped]
    E --> F[country · provider · blocklist · HTTPS with a verified certificate · target sites]
    F --> R[result with the outcome of every check]
```

Each check leaves a `Check` on the result (`checkstate.py`): `passed`, `failed`, `unavailable` or `skipped`, with a reason code, the target, the time, what was measured and what the result doesn't say. Two rules hold everywhere: a check that didn't run is never `passed`, and a check target that is down doesn't fail the proxies checked against it. For the first target in a scan that is `JudgeWatch` (switch and re-check). For the later ones, and for the first one in `--diagnose` and `--pick --verify`, the checker asks the target directly after a failure, at most every few seconds, and only believes an answer that is newer than the failing check. What the states mean, which lists require which, and the reason codes: [check-states.md](check-states.md).

Only hits go through the later steps, so the expensive checks cost little. Every failure still counts for the source it came from, that's what the learning is built on. A hit is only recorded once its verdict is in: when `--want` or Ctrl+C stops the workers, proxies still being confirmed are neither working nor failed.

## The proxy server

```mermaid
flowchart LR
    CL[client] -->|first byte 0x05| S5[socks.py]
    CL -->|HTTP / CONNECT| H[http.py]
    CL -->|GET /__proxy-scraper/status · /metrics| ST[status.py]
    S5 --> CO[core.py]
    H --> CO
    CO --> PO[pool.py<br/>filter · sticky · strategy]
    PO --> UP[upstream.py<br/>connect through proxy]
    UP --> T[target]
```

The first packet of every connection is kept, so if a proxy stays silent or answers with garbage, the same packet goes to the next one without the client noticing. Upstream answers are screened until the final status line, so a proxy asking for a login (407) never reaches the client.

Failures come in three kinds. A proxy that doesn't answer, times out or speaks garbage counts against it right away. A proxy that answers but can't open the tunnel (CONNECT 502, SOCKS refusal) raises `TargetError`: that only counts against it if another proxy then reaches the same target, so a dead target never disables the pool. `Unsupported` (SOCKS4 and IPv6) never counts.

## Around the tool

```mermaid
flowchart LR
    GA[GitHub Actions<br/>every hour] -->|run + publish.py| PL[proxy-list branch<br/>lists · JSON · website]
    PL --> WEB[GitHub Pages<br/>live list website]
    PL -->|stats.json · proxies.json| BOT[bot/<br/>Discord bot]
    PL -->|all.txt| RL[--recheck live]
    PL -->|mirror.py| FPL[free-proxy-list repo<br/>lists only · per country]
```

`bot/` is a separate package with its own requirements (discord.py). It only reads the published JSON files, so it knows nothing about the tool's internals. `.github/workflows/bot.yml` tests it and deploys it to a server over SSH.

## State on disk

| Where | What |
|---|---|
| `data/source_stats.json` | hit rate per source, last change, fail streak |
| `data/proxy_history.json` | proxies that worked, with latency and details |
| `data/fetch-cache/` | ETags and parsed keys of the lists (gzip) |
| `data/geo/` | DB-IP country and provider databases, refreshed monthly |
| `results/<date>/` | one folder per run, `results/latest.txt` points to the newest |

Installed with pip/pipx, `data/` lives in the user data folder (`PROXY_SCRAPER_HOME` overrides it) and `results/` in the current directory.

## Decisions we measured

Some things look like obvious improvements and turned out not to be. Where an issue is linked, it has the numbers, unless noted.

- **Protocol detection before checking** ([#3](../../../issues/3)) – a third of the addresses are listed under all three types, but sniffing the protocol with an extra connection made runs slower (77 s vs 60 s). Dropped.
- **IPv6** ([#1](../../../issues/1)) – about 300 entries across all 726 sources, mostly V2Ray configs. Not worth it yet.
- **Check targets are ranked by quality, not latency** ([#8](../../../issues/8)) – in one comparison with the same 300 proxies, checkip.amazonaws.com gave 255 hits and ident.me 199, although ident.me answered faster. The measurement itself was not posted to the issue.
- **Content check** ([#46](../../../issues/46)) – in one early look, 54 of 270 proxies returned a different page than the reference; over the 3.6 million checks in [the numbers](free-proxies-in-numbers.md) it was 5.2 % of the proxies that got that far, about 90 per hourly run. No sample of those pages was kept, so why they differed isn't known. The count of 54 of 270 is from a commit message; the issue has no numbers. The check is always on, and a run now counts how many changed pages contain a `<script` tag.
- **Cloudflare is never a check target** – many "proxies" are Cloudflare addresses that would answer a request to a Cloudflare-hosted site themselves.
- **Blocklists** ([#66](../../../issues/66)) – Spamhaus refuses public resolvers, in one measurement of 708 exit IPs DroneBL listed 59 % (it's essentially a list of open proxies) and SpamCop 29 %. Only SpamCop is used, and only after a probe with the documented test address proves the resolver gets real answers.

## Testing

Everything runs offline: `tests/fakes.py` has real HTTP, SOCKS4 and SOCKS5 proxies, login-protected proxies and target sites on `localhost`, and `tests/lab.py` a whole lab: check targets that can go down, and proxies that each misbehave in one known way (another exit IP on the second request, a rewritten page, no CONNECT, a certificate that doesn't verify, a late answer). Network code is tested against those, not against mocks of our own functions. CI runs the suite on Linux, macOS and Windows with Python 3.9, 3.11, 3.13 and 3.14, builds the package, and does a real scan inside the Docker image.
