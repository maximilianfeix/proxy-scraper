# Contributing

Thanks for wanting to help! Bug reports, new proxy sources, ideas and pull requests are all welcome – in English or German.

## Quick ways to help

- **A source is missing?** Open a [new source](https://github.com/maximilianfeix/proxy-scraper/issues/new?template=new_source.yml) issue, or add it to [`proxyscraper/sources.json`](proxyscraper/sources.json) in a pull request.
- **Something broke?** Open a [bug report](https://github.com/maximilianfeix/proxy-scraper/issues/new?template=bug_report.yml) with the command and `proxy-scraper --version`.
- **Want to code?** Issues labelled [`good first issue`](https://github.com/maximilianfeix/proxy-scraper/labels/good%20first%20issue) or [`help wanted`](https://github.com/maximilianfeix/proxy-scraper/labels/help%20wanted) are a good start. Comment on the issue so nobody does the same work twice.

## Setup

```bash
git clone https://github.com/maximilianfeix/proxy-scraper.git
cd proxy-scraper
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

Running from the clone, learned state stays in `data/` and results in `results/` – both are ignored by git.

## Before you open a pull request

```bash
python3 -m pytest          # ~250 tests, offline, a few seconds
ruff check .
```

- **Tests run without internet.** They start real mini proxies, honeypots and target sites on `localhost` (see `tests/`). New checks or handshakes should come with a test like that.
- **UI changes:** attach a screenshot, and regenerate the README images with `python3 docs/make_demo.py`.
- **Python 3.9 compatible:** CI runs 3.9, 3.11 and 3.13 on Linux, macOS and Windows.
- **Dependencies:** the runtime only needs `rich` and `certifi`. Please discuss new ones in an issue first.
- The terminal UI text is German; code, comments in new modules, commits and pull requests can be English.

## Commits and pull requests

- One topic per pull request, linked to its issue (`Closes #123`).
- Commit messages in the imperative: “Add ETag cache for sources”, not “added …”.
- Every pull request gets an automatic review; please answer or resolve the comments.

## Releases

Maintainers bump `__version__` in `proxyscraper/__init__.py`, update `CHANGELOG.md` and push a `vX.Y.Z` tag – the release workflow does the rest.

By contributing you agree that your work is released under the [MIT License](LICENSE) and that you follow the [Code of Conduct](CODE_OF_CONDUCT.md).
