#!/usr/bin/env python3
"""
Proxy-Scraper: sammelt öffentliche HTTP/SOCKS4/SOCKS5-Proxys aus hunderten Quellen,
prüft sie parallel mit reinem asyncio (eigene Handshakes, kein HTTP-Client-Overhead)
und schreibt die funktionierenden Proxys nach results/<datum>/.

Quellen stehen in sources.json, dazu kommen Meta-Quellen (fremd gepflegte Quellenlisten)
und automatisch auf GitHub gefundene Listen. Pro Quelle wird gelernt, wie viele ihrer Proxys
funktionieren (data/source_stats.json); bekannte funktionierende Proxys (data/proxy_history.json)
werden zuerst geprüft.

Nutzung:
    python3 proxy_scraper.py
    python3 proxy_scraper.py --want 50 --https-only
    python3 proxy_scraper.py --help
"""

import sys

try:
    import uvloop  # optional, macht asyncio nochmal schneller

    uvloop.install()
except ImportError:
    pass

from proxyscraper.cli import run

if __name__ == "__main__":
    sys.exit(run())
