# Changelog

All notable changes to this project are listed here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- Proxy server: `/__proxy-scraper/metrics` in the Prometheus text format (requests, bytes, pool size and median latency per type), no extra dependency ([#67](https://github.com/maximilianfeix/proxy-scraper/issues/67))
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
- “Nächste Schritte” panel after a run with ready-to-copy commands ([#27](https://github.com/maximilianfeix/proxy-scraper/issues/27))
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

[Unreleased]: https://github.com/maximilianfeix/proxy-scraper/compare/v1.4.0...HEAD
[1.4.0]: https://github.com/maximilianfeix/proxy-scraper/compare/v1.3.0...v1.4.0
[1.3.0]: https://github.com/maximilianfeix/proxy-scraper/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/maximilianfeix/proxy-scraper/compare/v1.0.0...v1.2.0
[1.0.0]: https://github.com/maximilianfeix/proxy-scraper/releases/tag/v1.0.0
