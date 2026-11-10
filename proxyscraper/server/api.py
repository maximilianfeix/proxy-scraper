"""Proxy pool API on the same port as the rotating proxy – for programs that want a proxy address, not a proxy.

    curl http://127.0.0.1:8899/get                     one proxy, chosen like a connection would be
    curl http://127.0.0.1:8899/get?country=DE&https=1  with filters
    curl http://127.0.0.1:8899/all?format=txt          every usable proxy, best first, one URL per line

The endpoints and the JSON fields follow jhao104/proxy_pool (/get, /pop, /all, /count, /delete), so code
written for it works unchanged – plus our own fields and filters. A proxy request always carries an absolute URL
(GET http://…) or CONNECT, so a plain "GET /get" can't be mistaken for one.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlsplit

from ..parsing import PROXY_TYPES
from ..ui.widgets import shown_proxy
from .pool import PoolEntry

API_PREFIX = b"GET /"
ANONYMITY_RANK = {"transparent": 0, "anonymous": 1, "elite": 2}
TRUE = {"1", "true", "yes", "on"}
TEXT_TYPE = b"text/plain; charset=utf-8"
JSON_TYPE = b"application/json"
CHANGING = {"/pop", "/delete", "/report"}  # endpoints that change the pool – never from another website
ENDPOINTS = {
    "/get": "one proxy, chosen by the rotation strategy",
    "/pop": "like /get, and the proxy leaves the pool",
    "/all": "every usable proxy, best first (limit=N)",
    "/count": "how many proxies, by type and country",
    "/delete?proxy=IP:PORT": "take a proxy out of the pool",
    "/report?proxy=IP:PORT&ok=0": "tell the pool a proxy failed you (three in a row and it's out)",
}
FILTERS = {
    "type": "https (proxy_pool style) or http, socks4, socks5",
    "protocol": "http, socks4 or socks5 (comma-separated for several)",
    "country": "two-letter codes, e.g. DE,AT,CH",
    "https": "1 = only proxies that passed the verified TLS test",
    "anonymity": "anonymous or elite (at least)",
    "max_latency": "milliseconds",
    "format": "txt = plain proxy URLs instead of JSON",
}

Response = Tuple[bytes, bytes, bytes]  # status, content type, body


class BadRequest(ValueError):
    pass


def handle(pool: Any, target: bytes, show_credentials: bool = False) -> Response:
    """target: the request target, e.g. b"/get?country=DE". -> (status, content type, body).

    show_credentials: hand out upstream logins (user:password@) in full – only when the API itself wants a
    password (--serve-password); otherwise they're masked like on the status page."""
    parts = urlsplit(target.decode("latin-1"))
    path = endpoint(target)
    query = {k.lower(): v[-1] for k, v in parse_qs(parts.query).items()}
    text = query.get("format", "").lower() == "txt"
    try:
        if path == "/":
            return _json({"name": "proxy-scraper", "endpoints": ENDPOINTS, "filters": FILTERS})
        if path in ("/get", "/pop"):
            entry = pool.choose([e for e in pool.usable if _matcher(query)(e)])
            if entry is None:
                return _not_found("no proxy matches", text)
            if path == "/pop":
                pool.remove(entry)
            if text:
                return b"200 OK", TEXT_TYPE, _url(entry, show_credentials).encode() + b"\n"
            return _json(describe(entry, show_credentials))
        if path == "/all":
            matches = [e for e in pool.usable if _matcher(query)(e)]  # the pool keeps them best first
            limit = _int(query, "limit")
            if limit is not None:
                matches = matches[:max(limit, 0)]
            if text:
                return b"200 OK", TEXT_TYPE, "".join(f"{_url(e, show_credentials)}\n" for e in matches).encode()
            return _json([describe(e, show_credentials) for e in matches])
        if path == "/count":
            return _json({"count": count(pool.usable)})
        if path in ("/delete", "/report"):
            entry = _find(pool, query.get("proxy", ""))
            if entry is None:
                return _not_found("proxy not in the pool", text)
            if path == "/delete":
                pool.remove(entry)
            else:
                pool.report(entry, query.get("ok", "0").lower() in TRUE)
            return _json({"code": 0, "src": "success", "proxy": _proxy(entry, show_credentials),
                          "disabled": entry.disabled})
    except BadRequest as e:
        return b"400 Bad Request", JSON_TYPE, json.dumps({"code": 1, "error": str(e)}).encode()
    return b"404 Not Found", JSON_TYPE, json.dumps({"error": f"unknown path {path}, try / for the list of endpoints"}
                                                   ).encode()


def endpoint(target: bytes) -> str:
    """b"/delete/?proxy=…" -> "/delete" – the path handle() acts on."""
    return urlsplit(target.decode("latin-1")).path.rstrip("/") or "/"


def describe(entry: PoolEntry, show_credentials: bool = False) -> Dict[str, Any]:
    """Our fields plus the ones proxy_pool clients read (proxy, https, region, anonymous, check_count, …).
    A login in the proxy is masked ('alice:•••@1.2.3.4:1080') unless show_credentials."""
    r = entry.result
    return {
        "proxy": _proxy(entry, show_credentials),
        "url": _url(entry, show_credentials),
        "type": r.ptype,
        "https": bool(r.https),
        "country": r.country,
        "anonymity": r.anonymity,
        "latency_ms": r.latency,
        "speed_kbps": r.speed_kbps,
        "exit_ip": r.exit_ip,
        "datacenter": r.hosting,
        "blocklisted": r.blocklisted,
        # proxy_pool names
        "region": r.country,
        "anonymous": r.anonymity in ("anonymous", "elite"),
        "source": "proxy-scraper",
        "check_count": entry.ok + entry.fail,
        "fail_count": entry.fail,
        "last_status": not entry.disabled,
    }


def _proxy(entry: PoolEntry, show_credentials: bool) -> str:
    return entry.result.proxy if show_credentials else shown_proxy(entry.result.proxy)


def _url(entry: PoolEntry, show_credentials: bool) -> str:
    return entry.result.url if show_credentials else f"{entry.result.ptype}://{shown_proxy(entry.result.proxy)}"


def count(entries: List[PoolEntry]) -> Dict[str, Any]:
    countries: Dict[str, int] = {}
    for e in entries:
        if e.result.country:
            countries[e.result.country] = countries.get(e.result.country, 0) + 1
    return {
        "total": len(entries),
        "https": sum(1 for e in entries if e.result.https),
        "by_type": {t: sum(1 for e in entries if e.result.ptype == t) for t in PROXY_TYPES},
        "by_country": dict(sorted(countries.items(), key=lambda kv: (-kv[1], kv[0]))),
    }


def _matcher(query: Dict[str, str]) -> Callable[[PoolEntry], bool]:
    types = {t.strip().lower() for t in query.get("protocol", "").split(",") if t.strip()}
    https = query.get("https", "").lower() in TRUE
    kind = query.get("type", "").lower()
    if kind == "https":        # proxy_pool: type=https means "can do HTTPS"
        https = True
    elif kind:
        types.add(kind)
    unknown = types - set(PROXY_TYPES)
    if unknown:
        raise BadRequest(f"unknown protocol {', '.join(sorted(unknown))} (possible: {', '.join(PROXY_TYPES)})")
    countries = {c.strip().upper() for c in query.get("country", "").split(",") if c.strip()}
    anonymity = query.get("anonymity", "").lower()
    if anonymity and anonymity not in ANONYMITY_RANK:
        raise BadRequest("anonymity must be anonymous or elite")
    max_latency = _int(query, "max_latency")

    def matches(entry: PoolEntry) -> bool:
        r = entry.result
        return ((not types or r.ptype in types)
                and (not https or bool(r.https))
                and (not countries or r.country in countries)
                and (not anonymity or ANONYMITY_RANK.get(r.anonymity, -1) >= ANONYMITY_RANK[anonymity])
                and (max_latency is None or r.latency <= max_latency))
    return matches


def _find(pool: Any, proxy: str) -> Optional[PoolEntry]:
    """By 'ip:port' or a full URL ('socks5://ip:port') – with a URL the type has to match too. A proxy with a
    login is also found by its address alone, since the login is masked in the answers without a password."""
    proxy = proxy.strip()
    if not proxy:
        raise BadRequest("proxy=IP:PORT is missing")
    ptype, sep, address = proxy.rpartition("://")
    for entry in pool.entries:
        known = entry.result.proxy
        if address in (known, known.rpartition("@")[2]) and (not sep or entry.result.ptype == ptype.lower()):
            return entry
    return None


def _int(query: Dict[str, str], name: str) -> Optional[int]:
    if name not in query:
        return None
    try:
        return int(query[name])
    except ValueError:
        raise BadRequest(f"{name} must be a whole number") from None


def _json(payload: Any) -> Response:
    return b"200 OK", JSON_TYPE, json.dumps(payload, indent=1, ensure_ascii=False).encode()


def _not_found(message: str, text: bool) -> Response:
    # proxy_pool answers "no proxy" with this body – clients check .get("proxy"), so keep it JSON unless txt was asked
    if text:
        return b"404 Not Found", TEXT_TYPE, b""
    return b"404 Not Found", JSON_TYPE, json.dumps({"code": 0, "src": "no proxy", "error": message}).encode()
