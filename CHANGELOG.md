# Changelog

All notable changes to this project are listed here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Changed
- Terminal: the final report shows the datacenter and blocklist shares next to HTTPS and anonymity, the wizard panel no longer repeats the name from the banner ([#91](https://github.com/maximilianfeix/proxy-scraper/issues/91))
- Website: WCAG 2.1 AA fixes (3:1 borders on controls, a pause button for the ticker, keyboard-accessible copying, sort buttons, table caption, skip link), link previews with an image, a touch icon, a section documenting the JSON files, and `/` to jump to the search ([#79](https://github.com/maximilianfeix/proxy-scraper/issues/79), [#80](https://github.com/maximilianfeix/proxy-scraper/issues/80))
- README redesigned to match the website: brand-colored badges and buttons, the five checks as a diagram, headings without emojis, a section for the Discord bot. The German README is gone, everything is English now ([#73](https://github.com/maximilianfeix/proxy-scraper/issues/73))
- Everything is in English now: terminal UI, CLI help, messages, code comments, tests and the generated proxy-list README. Numbers use English formatting (12,345 and 1.5%), and the terminal uses the lime brand color ([#72](https://github.com/maximilianfeix/proxy-scraper/issues/72))
- New website design and a real logo: the route through a proxy that forms a check mark. Big live numbers, a ticker with the fastest proxies, a scroll scene through the five checks, smooth scrolling, light and dark theme. The README banner uses the same look

### Added
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

[Unreleased]: https://github.com/maximilianfeix/proxy-scraper/compare/v1.5.0...HEAD
[1.5.0]: https://github.com/maximilianfeix/proxy-scraper/compare/v1.4.0...v1.5.0
[1.4.0]: https://github.com/maximilianfeix/proxy-scraper/compare/v1.3.0...v1.4.0
[1.3.0]: https://github.com/maximilianfeix/proxy-scraper/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/maximilianfeix/proxy-scraper/compare/v1.0.0...v1.2.0
[1.0.0]: https://github.com/maximilianfeix/proxy-scraper/releases/tag/v1.0.0
