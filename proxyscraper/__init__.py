"""Proxy-Scraper: sammelt öffentliche HTTP/SOCKS4/SOCKS5-Proxys aus hunderten Quellen, prüft sie
parallel mit eigenen Protokoll-Handshakes und lernt, welche Quellen gute Proxys liefern."""

__version__ = "1.5.0"


def __getattr__(name):
    # Python-API erst bei Bedarf laden – "import proxyscraper" soll leicht bleiben (die CLI braucht sie nicht)
    if name in ("find_proxies", "find_proxies_async", "check_proxies", "check_proxies_async"):
        from . import api
        return getattr(api, name)
    raise AttributeError(f"module 'proxyscraper' has no attribute {name!r}")
