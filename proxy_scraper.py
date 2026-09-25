#!/usr/bin/env python3
"""
proxy-scraper: collects public HTTP/SOCKS4/SOCKS5 proxies from hundreds of sources,
checks them in parallel with plain asyncio (own handshakes, no HTTP client overhead)
and writes the working proxies to results/<date>/.

Sources live in proxyscraper/sources.json, plus meta sources (source lists maintained by others)
and lists found automatically on GitHub. For every source it learns how many of its proxies
work (data/source_stats.json); known working proxies (data/proxy_history.json) are checked first.

Usage:
    python3 proxy_scraper.py
    python3 proxy_scraper.py --want 50 --https-only
    python3 proxy_scraper.py --help
"""

import sys

from proxyscraper.cli import run

if __name__ == "__main__":
    sys.exit(run())
