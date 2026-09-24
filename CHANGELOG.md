# Changelog

All notable changes to this project are listed here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

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

[Unreleased]: https://github.com/maximilianfeix/proxy-scraper/compare/v1.2.0...HEAD
[1.2.0]: https://github.com/maximilianfeix/proxy-scraper/compare/v1.0.0...v1.2.0
[1.0.0]: https://github.com/maximilianfeix/proxy-scraper/releases/tag/v1.0.0
