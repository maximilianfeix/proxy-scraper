# How proxy-scraper compares

Two comparisons: with other **tools** that find and check proxies, by what you'd actually do with them, and with other **lists**. Tools were read on **2026-10-13** (README, config and source at the then-current commits). Lists were read on **2026-10-11** from their READMEs and re-checked on 2026-10-13 against one data file and the GitHub API where noted. Nothing here was benchmarked: there is no "faster" or "safer" on this page, because none of it was measured. "Not documented" means the project doesn't say, not that it doesn't happen. Corrections are welcome, open an issue or a PR.

## Tools, task by task

Compared with [monosans/proxy-scraper-checker](https://github.com/monosans/proxy-scraper-checker) (Rust, single binary), [jhao104/proxy_pool](https://github.com/jhao104/proxy_pool) (Python + Redis) and [bluet/proxybroker2](https://github.com/bluet/proxybroker2) (Python, the maintained fork of ProxyBroker).

### Get a few recently checked proxies

| | What you do | How recent, and can you see it |
|---|---|---|
| **proxy-scraper** | `uvx proxy-scraper-cli --pick 5`, or `--pick 5 --verify` to check them from your network first | Hourly list; with 1.30 every entry has its own `checked_at`. With `--verify`: checked seconds ago, time in `--json` |
| monosans | No pick command. `curl` the first lines of [monosans/proxy-list](https://github.com/monosans/proxy-list), or run a full scrape-and-check | List re-checked every hour; the time is the commit's, per list |
| proxy_pool | Start Redis, the scheduler and the server, then `curl 127.0.0.1:5010/all/` | Pool re-checked every 2 minutes; `last_time` per proxy. HTTP proxies only |
| proxybroker2 | `python -m proxybroker find --types HTTP --limit 5` | Checked during the command. No time in the output |

If you already run Redis and want a pool that keeps itself fresh, proxy_pool does that out of the box. If you want five proxies without setting anything up, proxy-scraper or the monosans list.

### Check a list of your own

| | What you do |
|---|---|
| **proxy-scraper** | `proxy-scraper --recheck file.txt`, a URL, or `cat list \| proxy-scraper --recheck - -o -`. From Python: `check_proxies([...])` |
| monosans | Put the file into `config.toml` in place of the default sources, run |
| proxy_pool | Write a fetcher class; there is no command for it |
| proxybroker2 | `python -m proxybroker find --data ./proxies.txt` |

### Understand why a proxy failed

| | What you can see |
|---|---|
| **proxy-scraper** | `--diagnose PROXY`: every check with `passed`, `failed`, `unavailable` or `skipped`, a reason code, the target and the time, as text or JSON. The same per kept proxy in `proxies.json`, and counted by reason in `run.json`. New in 1.30; before that, nothing per proxy |
| monosans | `debug = true`: one line of error text per failed proxy |
| proxy_pool | `fail_count` and pass/fail log lines; the validators swallow the reason |
| proxybroker2 | `--log DEBUG` with per-protocol steps, `--show-stats` with buckets (timeout, failed, wrong protocol or level), `proxy.get_log()` from Python |

proxybroker2 shows more of the protocol negotiation. What proxy-scraper adds is the difference between "failed" and "could not be checked", and the states in machine-readable output.

### Run a local pool or a rotating endpoint

| | What exists |
|---|---|
| **proxy-scraper** | `--serve`: one forward proxy on 127.0.0.1 (HTTP and SOCKS5 in), country, type and session through the login name, four rotation strategies, optional password, metrics, plus a `/get` `/pop` `/all` API. No database |
| monosans | None, it writes files and exits |
| proxy_pool | A pool API (`/get`, `/pop`, `/all`, …), not a forward proxy: your client fetches an address and connects itself. State in Redis, so several machines can share it |
| proxybroker2 | `serve`: a rotating forward proxy with error-rate and response-time limits; one strategy |

For a shared, persistent pool behind Redis, proxy_pool is the better fit. proxy-scraper's pool API uses the same paths and most of the same JSON fields, but not all: it has no `last_time`, its `anonymous` is true/false where proxy_pool's is a string, and `source` is always `proxy-scraper`.

### Use the results from Python

| | How |
|---|---|
| **proxy-scraper** | `find_proxies`, `check_proxies`, `live_proxies`, `ProxyRotator`; sync and async; each result has `.checks` |
| monosans | No library; read the JSON it writes |
| proxy_pool | HTTP calls to its API, or read Redis |
| proxybroker2 | `Broker`, asyncio only, results through a queue |

### What each one checks

| | **proxy-scraper** | monosans | proxy_pool | proxybroker2 |
|---|---|---|---|---|
| Protocols | HTTP, SOCKS4, SOCKS5 | HTTP, SOCKS4, SOCKS5 | HTTP | HTTP, HTTPS, SOCKS4, SOCKS5, CONNECT:80/25 |
| The check | exit IP from a check target, a second site that has to see the same IP, a static page that has to arrive byte for byte | one full fetch of `https://ipv4.icanhazip.com` by default | `HEAD http://httpbin.org`, then `HEAD https://www.qq.com` | a "judge" page that has to echo a marker, referer and cookie |
| TLS certificate verified | in the separate HTTPS test (one host); a proxy without HTTPS is still listed, with `https: false` | yes, in the main check with the default settings | no (`verify=False`) | off by default (`--verify-ssl`) |
| Anonymity level | yes | no | field exists, never set | yes |
| "Could not be checked" apart from "failed" | yes, per check (1.30) | no | only "not checked yet" (`last_status` empty) | no |
| IPv6 | no | not verified | not verified | yes |

Where the others are the better choice:

- **monosans/proxy-scraper-checker** if you don't want Python: one binary with signed build provenance, and with the default settings every proxy it keeps passed a TLS-verified fetch (whether its published list is built with the defaults was not verified). It has 27 times the stars.
- **jhao104/proxy_pool** for a long-running shared pool with a 2-minute re-check loop and per-proxy counters, and by far the most stars of the four. HTTP only, and its HTTPS check doesn't verify certificates.
- **bluet/proxybroker2** for watching a negotiation fail step by step, for IPv6, and for cookie, referer and POST checks. Installed from git, pre-releases only, certificate verification off by default.
- **proxy-scraper** for a few checked proxies with no setup, checking a pasted list, seeing what each check found, and a local rotating endpoint without a database.

## Lists

| | [proxifly/free-proxy-list](https://github.com/proxifly/free-proxy-list) | [TheSpeedX/PROXY-List](https://github.com/TheSpeedX/PROXY-List) | [monosans/proxy-list](https://github.com/monosans/proxy-list) | [clarketm/proxy-list](https://github.com/clarketm/proxy-list) | **proxy-scraper** |
|---|:---:|:---:|:---:|:---:|:---:|
| Refreshed | every 5 minutes | "from time to time" | every hour | not clear: the last list commit is from March 2023, the repository was last pushed in March 2026 | about every hour |
| Proxy must complete a real request | "validated" | not documented | yes, a full URL fetch | "Google passed" per entry | yes, two sites that have to see the same exit IP |
| A test page has to arrive unchanged | not documented | not documented | not documented | not documented | yes, one static page, byte for byte |
| HTTPS tested with a verified certificate | `https` field, method not documented | not documented | yes, if the list is built with the checker's default settings (not verified) | not documented | yes, a separate test to one host |
| Outcome of each check per entry | no | no | no | no | yes, from 1.30 |
| Per-protocol files | txt, json, csv | txt | txt, json | txt | txt (json and csv hold all protocols together) |
| Per-country files | yes | no | no (country in JSON) | no (country per line) | yes, plus per site |
| Per entry | country, city, anonymity, https, score | – | latency, country, city, ASN | country, anonymity, Google passed | latency, country, ASN, anonymity, hoster flag, share of runs on the list |
| Re-check the list from your own network | no | no | separate tool | no | `--pick --verify`, `--recheck live` |

Sizes on 13 Oct 2026, from each project's own README or data: proxifly about 62,000, TheSpeedX about 7,900, monosans about 1,400, proxy-scraper about 1,300 to 3,100 over the day. We did not run the other lists through our checks, so this page says nothing about how many of their entries would pass. Size and quality are different questions, and only the first one is answered here.

What our own data says about lists in general is in [the numbers](free-proxies-in-numbers.md): about a quarter of an hourly list is on the list again a day later, about half when the 16 hosts with 50 or more entries each are left out. All of these lists, this one included, are checked from somewhere that isn't your network. That is what checking again from your own is for.

proxy-scraper reads some of these projects as sources, and its hourly list is in turn a built-in source of [monosans/proxy-scraper-checker](https://github.com/monosans/proxy-scraper-checker) and [gfpcom/free-proxy-list](https://github.com/gfpcom/free-proxy-list).
