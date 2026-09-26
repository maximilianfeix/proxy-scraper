"""proxy-scraper: collects public HTTP/SOCKS4/SOCKS5 proxies from hundreds of sources, checks them
in parallel with its own protocol handshakes and learns which sources deliver good proxies."""

__version__ = "1.7.0"


def __getattr__(name):
    # load the Python API only when needed – "import proxyscraper" should stay light (the CLI doesn't need it)
    if name in ("find_proxies", "find_proxies_async", "check_proxies", "check_proxies_async"):
        from . import api
        return getattr(api, name)
    raise AttributeError(f"module 'proxyscraper' has no attribute {name!r}")
