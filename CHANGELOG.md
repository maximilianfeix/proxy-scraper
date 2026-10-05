# Changelog

All notable changes to this project are listed here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- `--recheck -` checks a list piped in on stdin: plain `ip:port` lines (each tried as HTTP and SOCKS5), `type://ip:port`, logins, JSON or a pasted table – the same extraction as for sources, but every untyped line counts. A terminal on stdin gives a clear message instead of waiting ([#248](https://github.com/maximilianfeix/proxy-scraper/issues/248))

## [1.23.0] – 2026-10-02

### Added
- Python 3.14 support: tested in CI on Linux, macOS and Windows ([#229](https://github.com/maximilianfeix/proxy-scraper/issues/229)) – thanks [@sameer-dhande](https://github.com/sameer-dhande)
- The hourly lists in a repository of their own: [maximilianfeix/free-proxy-list](https://github.com/maximilianfeix/free-proxy-list) – every protocol, HTTPS, elite, stable, the big sites and now one list per country (`countries/de.txt`), plus JSON and CSV, with the numbers of the last run on its README. `proxyscraper/mirror.py` builds it after `publish.py`; the workflow pushes one commit per run and squashes the history at the start of every month. Without the `LIST_REPO_KEY` secret (forks) the step does nothing
- The README on the `proxy-list` branch links to it
- Quick start examples for Node.js, Go and curl with SOCKS5 in the free-proxy-list README ([#230](https://github.com/maximilianfeix/proxy-scraper/issues/230)) – thanks [@sameer-dhande](https://github.com/sameer-dhande)
- The daily snapshots also go to a Hugging Face dataset as Parquet, one file per UTC day with a `snapshot_date` column, when `HF_DATASET_REPO` and `HF_TOKEN` are set ([#188](https://github.com/maximilianfeix/proxy-scraper/issues/188)) – thanks [@arm21-afk](https://github.com/arm21-afk)
- A new source: the hproxy-com HTTP list, 1.3 % of 3,000 candidates working in a test run – thanks [@arm21-afk](https://github.com/arm21-afk)
- Country names for 22 more countries, so their proxies get a page on the website – thanks [@sujaljadhav14](https://github.com/sujaljadhav14)
- A live dashboard for the rotating server at `/__proxy-scraper/`: usable proxies, success rate, requests, traffic and uptime, a chart of requests per second, countries, the best proxies and the latest connections, refreshed every two seconds. Self-contained (no CDN, works offline), client data rendered only as text, a strict Content-Security-Policy with the script pinned by hash, and `--serve-password` protects it. `/__proxy-scraper/status` now also lists the latest connections (without who sent them and with upstream passwords masked) and the countries of the pool. Without `--serve-password`, the latest connections are only in answers to requests made to an IP address or `localhost` – a website using DNS rebinding can't read them ([#240](https://github.com/maximilianfeix/proxy-scraper/issues/240))
- [README.zh-CN.md](README.zh-CN.md): a Simplified Chinese README – install (with a PyPI mirror), the checks, the hourly list with GitHub Pages and jsDelivr for networks where raw.githubusercontent is unreliable, the proxy_pool-compatible API, the rotating server, Python, MCP and an FAQ. The English README links to it
- `brew install maximilianfeix/tap/proxy-scraper` in the install section of both READMEs. The formula in [maximilianfeix/homebrew-tap](https://github.com/maximilianfeix/homebrew-tap) updates itself within about a day of each release
- `--export pac` writes `proxy.pac` for browsers, FoxyProxy and the OS proxy settings: the best 30 HTTP and SOCKS5 proxies in order, local names and private IPv4 addresses direct, no `DIRECT` fallback, no DNS lookups and no SOCKS4 (which would resolve names locally), ES5 so Windows' PAC engine runs it, failing closed when there are no proxies. The live list publishes it every hour as `proxy.pac` ([#242](https://github.com/maximilianfeix/proxy-scraper/issues/242))
- Recipe: the rotating server as the upstream of Burp Suite, OWASP ZAP and mitmproxy, with where to set it in each and why ZAP needs its HTTP (not SOCKS) setting; tested end to end with mitmproxy ([#244](https://github.com/maximilianfeix/proxy-scraper/issues/244))

### Changed
- "Best first" now counts how likely a proxy is still up. Over a week of hourly runs, 25 % of new proxies were listed again an hour later, 99 % of those listed for a day. The published lists, the pages, the website, `--pick`, `live_proxies()`, `ProxyRotator` and the MCP tools rank by page time divided by that chance, so the first lines of a file hold proxies that last: on the list of 2026-09-29 the share of the top 50 expected to still work went from 67 % to 88 %, with the median page time from 1.1 to 1.4 s. Own scans have no streaks and rank by speed as before

### Fixed
- README and ARCHITECTURE quoted early measurements ("one in five" proxies inject scripts, "5 out of 6" hits are honeypots, 450+ tests) – now the numbers from 3.6 million checks (one in 40, 54 %) and 760+ tests

## [1.22.0] – 2026-09-29

### Added
- Website: a format picker next to "Copy filtered" and the downloads – `type://ip:port`, plain `ip:port`, JSON or CSV. The choice is remembered in the browser
- A one-time hint after the second run that found proxies, pointing to the GitHub repo. Only in an interactive terminal, never in CI (`CI` set) or with `PROXY_SCRAPER_NO_STAR_HINT=1`
- [docs/free-proxies-in-numbers.md](docs/free-proxies-in-numbers.md): what 24 hourly runs (3.6 million checks) and a week of lists found

### Fixed
- Website: the proxy table fits the page from 360 px phones to wide screens. Before, the provider column sat behind a sideways scroll even at 1440 px, and on phones the latency was cut off. Narrower screens drop the least needed columns (provider, then HTTPS and "Gets through", then speed), and "Gets through" shows two sites and a "+N" count so rows stay one line high

## [1.21.0] – 2026-09-28

### Added
- Proxy pool API on the `--serve` port: `/get`, `/pop`, `/all`, `/count`, `/delete` and `/report`, with filters for country, protocol, HTTPS, anonymity and latency, and `format=txt` for plain URLs. Endpoints and JSON fields follow jhao104/proxy_pool, so code written for it works unchanged. With `--serve-password` it wants the password as Basic auth, like the status page
- `--source URL|FILE` (repeatable) adds your own proxy lists – URLs or local files, any text with ip:port, `socks5=…` fixes the type. They are never skipped by the learned source ranking. `--only-sources` loads nothing else, and the history then only reorders proxies from these lists

## [1.20.0] – 2026-09-28

### Added
- `ProxyRotator.proxy_url()`: one local proxy address for requests, httpx, Playwright, Scrapy or curl that rotates through the live list behind the scenes – best first, with failover, HTTPS only through verified-TLS proxies, country and protocol from the rotator. `playwright_proxy()` gives the same as Playwright's proxy settings. It takes over each new hourly list by itself ([#215](https://github.com/maximilianfeix/proxy-scraper/issues/215))

## [1.19.0] – 2026-09-28

### Changed
- The published lists (all.txt, http.txt, socks5.txt, …, proxies.json), the country and protocol pages and the website now come best first too: by first answer plus the download speed of the last check, like `--pick` since 1.18. Whoever takes the first lines of a file gets the ones that load pages. The website has a "Best first" button to go back after sorting by a column ([#212](https://github.com/maximilianfeix/proxy-scraper/issues/212))

## [1.18.0] – 2026-09-28

### Changed
- "Fastest first" now counts the download too, not just the first answer: `--pick`, `live_proxies()`, `ProxyRotator`, the MCP server's fetch_url and the action rank proxies from the live list by the speed measured in the last check. With real pages, the first 25 HTTPS proxies loaded 26 of 50 pages (median 2.8 s) instead of 4 of 50 (20 s). Own scans without speed data rank by latency as before ([#186](https://github.com/maximilianfeix/proxy-scraper/issues/186))

### Added
- `--pick --min-speed KBPS`, `live_proxies(min_speed=…)` already had it, and `min-speed` for the GitHub Action ([#186](https://github.com/maximilianfeix/proxy-scraper/issues/186))

## [1.17.0] – 2026-09-28

### Added
- The country and protocol pages (like /country/de/ or /socks5/) got a real overview: how many work right now, tunnel HTTPS, stayed on the list all week and get through to Google, the median speed, speed/uptime/sites per proxy in the table, the ready-made `--pick` and curl commands for exactly that selection, and answers to the usual questions ([#207](https://github.com/maximilianfeix/proxy-scraper/issues/207))

## [1.16.0] – 2026-09-28

### Added
- `ProxyRotator` in the Python API: `rotator.get(url)` loads a page through the hourly list and switches to the next proxy when one fails – the loop every scraper writes by hand, on the same failover as `--serve` and the MCP server's fetch_url. Sync and async ([#204](https://github.com/maximilianfeix/proxy-scraper/issues/204))

## [1.15.0] – 2026-09-27

### Added
- A Telegram bot: `/proxy de socks5` answers with a fast proxy and a curl line to try it, `/proxies 10 us https` with a short list, `/stats` with the last run. It runs in the same process as the Discord bot, needs only a `TELEGRAM_TOKEN` secret, and uses long polling – no open port ([#187](https://github.com/maximilianfeix/proxy-scraper/issues/187))

## [1.14.0] – 2026-09-27

### Added
- `proxy-scraper --pick [N]`: proxies from the hourly checked list in about half a second, no scan – with the usual filters plus `--min-uptime` and `--works-on`, only the URLs on stdout, so `curl -x "$(proxy-scraper --pick)"` works ([#199](https://github.com/maximilianfeix/proxy-scraper/issues/199))

## [1.13.0] – 2026-09-27

### Added
- Website: "Why this list, not another one" – for each thing you'd want to know about a proxy, what a typical free list tells you and what this one measured in the last run, with live numbers. And an FAQ (safety, why free proxies die, updates, license, Python and AI agents) with FAQPage structured data for search engines ([#196](https://github.com/maximilianfeix/proxy-scraper/issues/196))

## [1.12.0] – 2026-09-27

### Added
- A bookmarklet: drag "Get a proxy" from the website to the bookmarks bar, and one click on any page copies a proxy that was on the list in 90 %+ of this week's checks. Plus "copy a reliable one now" right on the site ([#189](https://github.com/maximilianfeix/proxy-scraper/issues/189))

### Changed
- The steps after a run (site check, speed) share their plumbing in `runsteps.py`, and nothing outside the checker touches its private TLS tunnel anymore ([#192](https://github.com/maximilianfeix/proxy-scraper/issues/192))

### Fixed
- Website: long country names wrapped in the Countries chart, the labels share one column now

## [1.11.0] – 2026-09-27

### Added
- An Atom feed for the weekly report (report/feed.xml): one entry per week, to follow it in a feed reader or pipe it into Slack, Discord or Mastodon ([#185](https://github.com/maximilianfeix/proxy-scraper/issues/185))
- Instagram and TikTok in the check of which sites let a proxy through – on the website, in works-with/, the MCP server and `live_proxies()`. Measured first: ChatGPT, eBay and Indeed block every proxy and LinkedIn and Twitch let all of them through, so those would say nothing
- Daily snapshots: the first run of each UTC day keeps its proxies.json for good, gzipped, as an asset of that year's `snapshots-YYYY` release ([#143](https://github.com/maximilianfeix/proxy-scraper/issues/143))
- Download speed per proxy: after every run each HTTPS-capable proxy downloads 100 KB from Cloudflare's speed test, 12 s at most, timed from the request to the last byte. `speed_kbps` in proxies.json and the CSV, a sortable Speed column on the website (the Anonymity column made room – the Elite filter is still there), on the proxy pages and in the weekly report, `min_speed` in `live_proxies()` and `min_speed_kbps` in the MCP server ([#140](https://github.com/maximilianfeix/proxy-scraper/issues/140))

### Fixed
- The same GitHub file through jsDelivr or githack counted as a separate source and was downloaded twice – mirrors are mapped to the original raw URL now
- Website: sorting by a column with gaps (speed, uptime) put the proxies without a value in between – they always go last now

## [1.10.0] – 2026-09-27

### Added
- A GitHub Action: `uses: maximilianfeix/proxy-scraper@v1` gives any workflow working proxies – same filters as `live_proxies()`, optionally rechecked from the runner, outputs `proxy`, `file` and `count` ([#178](https://github.com/maximilianfeix/proxy-scraper/issues/178))
- Website: a world map of where the working proxies are – hover for the count, click a country to filter the list. And the page stays live: it shows when the next check is due and loads the new list by itself when it lands ([#176](https://github.com/maximilianfeix/proxy-scraper/issues/176))
- Tab completion for PowerShell: `proxy-scraper --completion powershell | Out-String | Invoke-Expression`. Options with their help, the choices after an option, paths where a file goes. Tested against a real pwsh via TabExpansion2 ([#114](https://github.com/maximilianfeix/proxy-scraper/issues/114))
- `--export singbox`: a sing-box config with a local HTTP+SOCKS proxy on 127.0.0.1:2080 and a urltest group over all proxies, SOCKS4 included. Checked with `sing-box check` and a real run ([#113](https://github.com/maximilianfeix/proxy-scraper/issues/113))
- `--list-sources --json` prints the source ranking as JSON for scripts ([#115](https://github.com/maximilianfeix/proxy-scraper/issues/115))

### Fixed
- A result file line with a Unicode digit ("1.2.3.4:²") crashed the parser – found by the new fuzz tests
- Proxy server: when a free proxy hung up in the middle of an upload, uvloop reported it as RuntimeError, the handler died and the failure was never counted against that proxy
- The Amazon check counted nearly every proxy as "through": Amazon now answers bots with a 2 KB stub page and status 200, even without a proxy. It checks the search page now and only counts a 200 with a real page behind it

### Tests
- Property-based tests for the parser with hypothesis: random bytes and list-like text never crash it, every key it returns is well-formed with a public address, and every public address is found in every list format ([#120](https://github.com/maximilianfeix/proxy-scraper/issues/120))

## [1.9.0] – 2026-09-27

### Added
- A weekly report, rebuilt with every run: how long free proxies last (most are gone within the hour), how many get through to Google, Reddit and Amazon – datacenter exits vs the rest – and where they are. As a page (report/), as markdown to post and as a short post that fits on X
- A page per proxy on the website: protocol, country, provider, uptime, which big sites let it through, a timeline of every check this week and copy-ready curl/Python commands to test it from your own machine. Linked from the table; only proxies on the list for half the week or more are in the sitemap, the rest are noindex
- README recipes for httpx, aiohttp and Scrapy (a rotating downloader middleware), each tried against the live list ([#118](https://github.com/maximilianfeix/proxy-scraper/issues/118), [#119](https://github.com/maximilianfeix/proxy-scraper/issues/119))
- Lists that don't say their protocol (plain ip:port in a generic proxies.txt) are tried as HTTP and as SOCKS5. On 20,000 such entries 44 worked as HTTP and 32 as SOCKS5 – those 32 were missed before ([#44](https://github.com/maximilianfeix/proxy-scraper/issues/44))

## [1.8.1] – 2026-09-27

### Fixed
- Generic lists (proxies.txt, all.txt …) with plain ip:port lines gave nothing and were paused as "unreachable" – they're read as HTTP now: 64 more sources deliver
- The download cache stores parsed proxies, so a parser improvement never reached unchanged lists. It now reloads every list once when the parser changes
- Source statistics written by another version are read instead of thrown away

### Added
- Website: the filters live in the address, so a view can be shared or bookmarked (plus a Share view button), and the pages per protocol and country open the list with their filter. Countries show their names ([#116](https://github.com/maximilianfeix/proxy-scraper/issues/116), [#117](https://github.com/maximilianfeix/proxy-scraper/issues/117))
- Discovery also reads the source lists of other proxy scrapers (sources.json, config.toml, urls.txt …) and keeps every URL in them that really holds 20+ proxies – about 250 more sources in a test run

## [1.8.0] – 2026-09-27

### Added
- Which big sites let each proxy through: after every run the HTTPS-capable proxies are tried on Google, Reddit and Amazon, each with its own rule (Google's captcha redirect counts as blocked). `sites` in proxies.json, `works-with/google.txt` and friends, a filter and column on the website, `works_on` in the MCP server and in `live_proxies()` ([#139](https://github.com/maximilianfeix/proxy-scraper/issues/139))
- `live_proxies()` in the Python API: the hourly checked list with the same filters as `find_proxies`, plus `min_uptime` – no scan needed ([#141](https://github.com/maximilianfeix/proxy-scraper/issues/141))
- Website: the theme switch grows the new theme out of the button, and the rows settle in when filters or sorting change instead of snapping. The scroll-driven route only does its layout work while it's on screen (about 60 % fewer layout reads while scrolling)
- Uptime per proxy on the live list: `uptime_24h`, `uptime_7d` and `first_seen` in proxies.json, an Uptime column on the website, `stable.txt` with everything listed in 90 %+ of this week's runs, and `min_uptime_percent` in the MCP server's get_proxies ([#138](https://github.com/maximilianfeix/proxy-scraper/issues/138))
- Charts in the README, redrawn with every run: working proxies over the last week by protocol, and the top countries. Plus GitHub Pages and jsDelivr links for every list file ([#142](https://github.com/maximilianfeix/proxy-scraper/issues/142))

## [1.7.1] – 2026-09-26

### Changed
- On PyPI now: `pipx install proxy-scraper-cli` (the plain name is blocked by an older, similar package – the commands stay `proxy-scraper` and `proxy-scraper-mcp`). `proxy-scraper --mcp` starts the MCP server too, and each release publishes it to the official MCP registry as `io.github.maximilianfeix/proxy-scraper` ([#42](https://github.com/maximilianfeix/proxy-scraper/issues/42))

## [1.7.0] – 2026-09-26

### Added
- MCP server for AI agents: `proxy-scraper-mcp` gives Claude Code, Claude Desktop, Cursor, VS Code, Codex and other MCP clients three tools – `get_proxies` (instant, from the hourly list, with the website's filters), `check_proxies` (fresh from your own network, with progress) and `fetch_url` (a page through a verified proxy as readable text, with failover, verified TLS for HTTPS, and local or private targets refused, also after redirects). `pip install "proxy-scraper[mcp]"` on Python 3.10+, setup for every client in the README ([#129](https://github.com/maximilianfeix/proxy-scraper/issues/129))

### Changed
- More sources: 28 new curated lists (Databay, the full proxifly list, vakhov, freeproxy.world and 19 GitHub lists that bring proxies nobody else had), and the GitHub search now runs daily, keeps what earlier runs found for three weeks, asks 23 queries instead of 9 and skips VPN-config repos ([#127](https://github.com/maximilianfeix/proxy-scraper/issues/127))
- Website: calmer trend chart (no spikes from runs minutes apart), less empty space, the footer links no longer run into the wordmark ([#131](https://github.com/maximilianfeix/proxy-scraper/issues/131))

### Fixed
- Proxy server: stopping it ends open tunnels instead of leaving them running (on Python 3.12+ a tunnel whose target never hangs up could keep Ctrl+C waiting), its own 502 and 400 are marked with an `X-Proxy-Scraper` header, and IPv6 targets work in absolute `http://` URLs
- Result files are placed when they're written, not when the program starts, so embedding proxy-scraper (like the MCP server does) can move them

## [1.6.0] – 2026-09-26

### Changed
- The live list is refreshed every hour instead of every 6 hours (a full run takes about 3 minutes). "Stable" still means 24 hours, `stats.json` now says `run_hours`, and the Discord bot still posts a summary at most every 6 hours (`PROXYBOT_POST_EVERY_HOURS`) ([#111](https://github.com/maximilianfeix/proxy-scraper/issues/111))
- Terminal: the final report shows the datacenter and blocklist shares next to HTTPS and anonymity, the wizard panel no longer repeats the name from the banner ([#91](https://github.com/maximilianfeix/proxy-scraper/issues/91))
- Website: WCAG 2.1 AA fixes (3:1 borders on controls, a pause button for the ticker, keyboard-accessible copying, sort buttons, table caption, skip link), link previews with an image, a touch icon, a section documenting the JSON files, and `/` to jump to the search ([#79](https://github.com/maximilianfeix/proxy-scraper/issues/79), [#80](https://github.com/maximilianfeix/proxy-scraper/issues/80))
- README redesigned to match the website: brand-colored badges and buttons, the five checks as a diagram, headings without emojis, a section for the Discord bot. The German README is gone, everything is English now ([#73](https://github.com/maximilianfeix/proxy-scraper/issues/73))
- Everything is in English now: terminal UI, CLI help, messages, code comments, tests and the generated proxy-list README. Numbers use English formatting (12,345 and 1.5%), and the terminal uses the lime brand color ([#72](https://github.com/maximilianfeix/proxy-scraper/issues/72))
- New website design and a real logo: the route through a proxy that forms a check mark. Big live numbers, a ticker with the fastest proxies, a scroll scene through the five checks, smooth scrolling, light and dark theme. The README banner uses the same look

### Added
- The website gets a static page per protocol (HTTP, SOCKS4, SOCKS5, HTTPS, elite) and per country, each with a `proxies.txt`, plus a `sitemap.xml` and dataset markup, so search engines find the list ([#121](https://github.com/maximilianfeix/proxy-scraper/issues/121))
- `--serve-refill HOURS`: the running proxy server checks fresh proxies in the background and adds the hits, so it no longer runs dry over days; `compose.yaml` uses it ([#109](https://github.com/maximilianfeix/proxy-scraper/issues/109))
- `-o -` prints the hits to stdout for pipes, the interface goes to stderr then ([#105](https://github.com/maximilianfeix/proxy-scraper/issues/105))
- `--serve-password` / `PROXY_SCRAPER_SERVE_PASSWORD`: the rotating server can require a password (HTTP, SOCKS5 and the status page), plus a `compose.yaml` that runs it in Docker ([#103](https://github.com/maximilianfeix/proxy-scraper/issues/103))
- Discord bot: `/proxies not_blocklisted:true` and the blocklist status in `/proxy`
- Release workflow can publish to PyPI with trusted publishing (no token in the repo), switched on with the repository variable `PYPI_PUBLISH`; Dependabot also watches the Python dependencies of the tool and the bot ([#42](https://github.com/maximilianfeix/proxy-scraper/issues/42))
- Blocklist info for every exit IP (SpamCop, one cached DNS lookup each) and `--no-blocklisted` to skip listed ones; about 29 % of working proxies are listed. Skipped with a note when the DNS resolver is refused. The website shows a BL tag and a "Not blocklisted" filter ([#66](https://github.com/maximilianfeix/proxy-scraper/issues/66))
- Discord bot (`bot/`): posts every run of the live list with the fastest proxies and the full lists as files, sets up its own read-only channels, and answers `/proxies`, `/proxy`, `/stats` and `/about`. A GitHub Action tests it and deploys it to a server as a hardened systemd service ([#74](https://github.com/maximilianfeix/proxy-scraper/issues/74), [#75](https://github.com/maximilianfeix/proxy-scraper/issues/75))

### Fixed
- Learning: proxies still being confirmed when `--want` is reached or Ctrl+C is pressed no longer count as dead, a list with none of the requested `--types` is no longer paused as unreachable, and outdated lists get another look every 3 days instead of never ([#83](https://github.com/maximilianfeix/proxy-scraper/issues/83))
- Proxy server: a target that is down no longer gets working proxies disabled (a refused tunnel only counts against a proxy if another proxy reaches the same target), a client leaving in the middle of a request body no longer prints a traceback, a slow TLS ClientHello keeps the part that already arrived, and IPv6 targets work over HTTP CONNECT and SOCKS5 ([#82](https://github.com/maximilianfeix/proxy-scraper/issues/82))
- A `--recheck` file that is missing now gives a message instead of a traceback, `http://` lines without an address no longer crash the parser, your own IP must match a whole address before a proxy counts as transparent, `gh` is only asked for a token when discovery can run, and the last German strings are gone ([#84](https://github.com/maximilianfeix/proxy-scraper/issues/84))

## [1.5.0] – 2026-09-25

### Added
- Tab completion for bash, zsh and fish: `proxy-scraper --completion zsh` prints the script. It is generated from the options, so it never goes stale ([#62](https://github.com/maximilianfeix/proxy-scraper/issues/62))
- Python API: `find_proxies()` and `check_proxies()` (plus async versions) run the same checks as the CLI and return the hits; `docs/ARCHITECTURE.md` explains how the modules fit together ([#50](https://github.com/maximilianfeix/proxy-scraper/issues/50))
- Proxy server: `/__proxy-scraper/metrics` in the Prometheus text format (requests, bytes, pool size and median latency per type), no extra dependency ([#67](https://github.com/maximilianfeix/proxy-scraper/issues/67))
- Stable proxies: the live list remembers how many runs in a row each proxy worked (`streaks.json`); the website shows it and filters for 24 h+ ([#61](https://github.com/maximilianfeix/proxy-scraper/issues/61))
- `--recheck live` starts from the public live list and checks it again from your own network: about 30 s instead of a full scan ([#60](https://github.com/maximilianfeix/proxy-scraper/issues/60))
- `--serve-host` to make the proxy server reachable from outside a Docker container, with a warning when it's not a loopback address ([#43](https://github.com/maximilianfeix/proxy-scraper/issues/43))
- Provider (ASN and name) for every proxy from the offline DB-IP ASN database, a guess whether it's a datacenter, and `--no-datacenter` to skip those. About 45 % of working proxies exit from datacenters ([#49](https://github.com/maximilianfeix/proxy-scraper/issues/49))
- Proxy server: `--rotate weighted|random|round-robin|fastest`, `--sticky SEC`, per-request choice through the username (`country-de`, `type-socks5`, `session-NAME`), SOCKS5 on the same port, a JSON status endpoint, and disabled proxies are re-checked every 5 minutes ([#48](https://github.com/maximilianfeix/proxy-scraper/issues/48))
- The live list has a website on GitHub Pages: search, filters, copy and download, country and latency charts and a trend over the last runs ([#47](https://github.com/maximilianfeix/proxy-scraper/issues/47))
- Proxies that tamper with content are filtered out: a static HTML page has to arrive unchanged. On 270 working proxies, 54 injected something, mostly a `<script src="http://…">` ([#46](https://github.com/maximilianfeix/proxy-scraper/issues/46))

## [1.4.0] – 2026-09-25

### Added
- Proxies with credentials (`socks5://user:pass@…`) are checked with their login instead of losing it: Basic auth for HTTP, RFC 1929 for SOCKS5, user ID for SOCKS4. They're never published to the public live list ([#7](https://github.com/maximilianfeix/proxy-scraper/issues/7))
- Fallback check targets: before a run all targets are probed (Cloudflare-hosted ones are rejected), during the run a watchdog switches when the current one goes down. Proxies checked during the outage are re-checked and don't count for the source statistics ([#8](https://github.com/maximilianfeix/proxy-scraper/issues/8))
- Docker image (`ghcr.io/maximilianfeix/proxy-scraper`, amd64 + arm64) with volumes for learned state and results; CI runs a real scan inside the container ([#5](https://github.com/maximilianfeix/proxy-scraper/issues/5))
- `--export proxychains,clash,curl` (or `all`) writes ready-made configs next to the results ([#4](https://github.com/maximilianfeix/proxy-scraper/issues/4))

### Changed
- Countries are looked up offline in the DB-IP Lite database (downloaded once a month, 2 µs per lookup) instead of waiting for ip-api.com, which is now only a fallback. On 943 IPs it agreed with ip-api on 96 % ([#2](https://github.com/maximilianfeix/proxy-scraper/issues/2))
- Unchanged lists are no longer downloaded again: ETag / Last-Modified with a local cache of the parsed proxies. A second run right after the first went from 161 MB in 22 s to 0 MB in 9 s. `--no-cache` forces a full download ([#9](https://github.com/maximilianfeix/proxy-scraper/issues/9))
- The rotating server skips upstream proxies that answer `407 Proxy Authentication Required`, even after `100 Continue`

## [1.3.0] – 2026-09-24

### Added
- Installable as a real command-line tool: `pipx install git+https://github.com/maximilianfeix/proxy-scraper.git` gives you `proxy-scraper`, plus `python -m proxyscraper` and `--version` ([#26](https://github.com/maximilianfeix/proxy-scraper/issues/26))
- Release workflow: every version tag is tested, built, smoke-tested and published with a wheel
- “Next steps” panel after a run with ready-to-copy commands ([#27](https://github.com/maximilianfeix/proxy-scraper/issues/27))
- English README (German version in `README.de.md`), contributing guide, security policy, issue forms ([#28](https://github.com/maximilianfeix/proxy-scraper/issues/28))

### Changed
- Calmer, more consistent terminal UI: one colour palette, framed sections, clearer panel titles ([#27](https://github.com/maximilianfeix/proxy-scraper/issues/27))
- When installed, learned state lives in the user data folder (`PROXY_SCRAPER_HOME` overrides it) and results go to `./results`
- `sources.json` moved into the package

## [1.2.0] – 2026-09-24

### Added
- Setup wizard: started without arguments, the tool asks what you are looking for – presets or step by step – and shows the matching command line ([#12](https://github.com/maximilianfeix/proxy-scraper/issues/12))
- Rotating proxy server with `--serve` and silent failover; HTTPS only through proxies with verified TLS ([#15](https://github.com/maximilianfeix/proxy-scraper/issues/15))
- `--target` keeps only proxies that really reach a given site ([#14](https://github.com/maximilianfeix/proxy-scraper/issues/14))
- Live proxy list published every 6 hours by GitHub Actions on the `proxy-list` branch ([#18](https://github.com/maximilianfeix/proxy-scraper/issues/18))
- Windows support ([#6](https://github.com/maximilianfeix/proxy-scraper/issues/6))

### Changed
- Honeypots are filtered out: every hit must fetch a second, independent page with the same exit IP ([#20](https://github.com/maximilianfeix/proxy-scraper/issues/20))
- Filters make checking faster – `--max-latency` becomes the timeout, unneeded HTTPS tests are skipped ([#13](https://github.com/maximilianfeix/proxy-scraper/issues/13))
- Cleaner architecture: `RunOptions`, a run in phases, the UI as its own package ([#11](https://github.com/maximilianfeix/proxy-scraper/issues/11))
- Lint (ruff), CodeQL and Dependabot

## [1.0.0] – 2026-09-24

First public version.

- 700+ sources: curated list, meta sources and automatic GitHub discovery
- Hand-written HTTP, SOCKS4 and SOCKS5 handshakes, 2000+ checks in parallel
- HTTPS test, anonymity level and country for every hit
- Learns the hit rate per source and checks known proxies first
- Filters (`--country`, `--https-only`, `--anonymity`, `--max-latency`) and `--want N`
- Results as txt, json and csv under `results/`
- Live dashboard in the terminal

[Unreleased]: https://github.com/maximilianfeix/proxy-scraper/compare/v1.23.0...HEAD
[1.23.0]: https://github.com/maximilianfeix/proxy-scraper/compare/v1.22.0...v1.23.0
[1.22.0]: https://github.com/maximilianfeix/proxy-scraper/compare/v1.21.0...v1.22.0
[1.21.0]: https://github.com/maximilianfeix/proxy-scraper/compare/v1.20.0...v1.21.0
[1.20.0]: https://github.com/maximilianfeix/proxy-scraper/compare/v1.19.0...v1.20.0
[1.19.0]: https://github.com/maximilianfeix/proxy-scraper/compare/v1.18.0...v1.19.0
[1.18.0]: https://github.com/maximilianfeix/proxy-scraper/compare/v1.17.0...v1.18.0
[1.17.0]: https://github.com/maximilianfeix/proxy-scraper/compare/v1.16.0...v1.17.0
[1.16.0]: https://github.com/maximilianfeix/proxy-scraper/compare/v1.15.0...v1.16.0
[1.15.0]: https://github.com/maximilianfeix/proxy-scraper/compare/v1.14.0...v1.15.0
[1.14.0]: https://github.com/maximilianfeix/proxy-scraper/compare/v1.13.0...v1.14.0
[1.13.0]: https://github.com/maximilianfeix/proxy-scraper/compare/v1.12.0...v1.13.0
[1.12.0]: https://github.com/maximilianfeix/proxy-scraper/compare/v1.11.0...v1.12.0
[1.11.0]: https://github.com/maximilianfeix/proxy-scraper/compare/v1.10.0...v1.11.0
[1.10.0]: https://github.com/maximilianfeix/proxy-scraper/compare/v1.9.0...v1.10.0
[1.9.0]: https://github.com/maximilianfeix/proxy-scraper/compare/v1.8.1...v1.9.0
[1.8.1]: https://github.com/maximilianfeix/proxy-scraper/compare/v1.8.0...v1.8.1
[1.8.0]: https://github.com/maximilianfeix/proxy-scraper/compare/v1.7.1...v1.8.0
[1.7.1]: https://github.com/maximilianfeix/proxy-scraper/compare/v1.7.0...v1.7.1
[1.7.0]: https://github.com/maximilianfeix/proxy-scraper/compare/v1.6.0...v1.7.0
[1.6.0]: https://github.com/maximilianfeix/proxy-scraper/compare/v1.5.0...v1.6.0
[1.5.0]: https://github.com/maximilianfeix/proxy-scraper/compare/v1.4.0...v1.5.0
[1.4.0]: https://github.com/maximilianfeix/proxy-scraper/compare/v1.3.0...v1.4.0
[1.3.0]: https://github.com/maximilianfeix/proxy-scraper/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/maximilianfeix/proxy-scraper/compare/v1.0.0...v1.2.0
[1.0.0]: https://github.com/maximilianfeix/proxy-scraper/releases/tag/v1.0.0
