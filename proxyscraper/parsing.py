"""Finds proxies in any list format and normalizes them.

Proxies are kept everywhere as the key "type ip:port" (one string) – with more than a million
entries that saves a lot of memory compared to tuples.
"""

from __future__ import annotations

import ipaddress
import re
from typing import Iterable, List, Optional, Set, Tuple
from urllib.parse import unquote

from .handshake import format_auth

PROXY_TYPES = ("http", "socks4", "socks5")
TYPE_ALIASES = {
    "http": "http", "https": "http",
    "socks4": "socks4", "socks4a": "socks4",
    "socks5": "socks5", "socks5h": "socks5", "socks5a": "socks5",
    "auto": "auto", "mixed": "auto",
}

_IP = rb"((?:\d{1,3}\.){3}\d{1,3})"
# Schneller Standardfall: ip:port
PLAIN_RE = re.compile(rb"(?<![\d.])" + _IP + rb"\s*:\s*(\d{2,5})(?![\d.])")
# complete: additionally "ip port" and HTML tables like <td>1.2.3.4</td><td>8080</td>
PROXY_RE = re.compile(
    rb"(?<![\d.])" + _IP + rb"(?:\s*:\s*|[ \t]+|\s*(?:<[^<>]{0,100}>\s*){1,6})(\d{2,5})(?![\d.])"
)
# JSON APIs like {"ip": "1.2.3.4", ..., "port": "8080"} – in both orders
JSON_IP_PORT_RE = re.compile(rb'"ip"\s*:\s*"' + _IP + rb'"[^{}]{0,500}?"port"\s*:\s*"?(\d{2,5})')
JSON_PORT_IP_RE = re.compile(rb'"port"\s*:\s*"?(\d{2,5})"?[^{}]{0,500}?"ip"\s*:\s*"' + _IP + rb'"')
# type://[user:pass@]ip:port – here the type is in the line itself
SCHEME_RE = re.compile(
    rb"(?i)(?<![a-z0-9])(https?|socks4a?|socks5h?)://(?:([^\s@/]{1,100})@)?" + _IP + rb":(\d{2,5})(?!\d)"
)
SCHEME_TYPES = {k.encode(): v for k, v in TYPE_ALIASES.items() if v != "auto"}

# ip:port:user:pass – how paid proxy lists often write logins (#254). Exactly four parts; the user has no '@',
# the password may (it can't have a ':', there'd be no telling where it starts)
COLON_LOGIN_RE = re.compile(rb"(?<![\w.:])" + _IP + rb":(\d{2,5}):([^\s:@]{1,100}):([^\s:]{1,100})(?![\w:])")
_COLON_LOGIN_LINE = re.compile(r"((?:\d{1,3}\.){3}\d{1,3}:\d{1,5}):([^\s:@]+):([^\s:]+)")

RawCandidate = Tuple[str, bytes, bytes, bytes]  # type, ip, port, credentials (b"" without)


_SPACE_SEPARATED_RE = re.compile(rb"\d\.\d{1,3}[ \t]+\d{2,5}(?![\d.])")


# Bump whenever parsing finds different proxies in the same bytes: the fetch cache stores parsed keys and
# reloads every list once when this changes (2: plain lists of "auto" sources are read, 3: as http and socks5,
# 4: ip:port:user:pass logins)
PARSER_VERSION = 4


def _needs_full_regex(data: bytes) -> bool:
    """Only space/HTML lists need the slower regex (sample from the start of the file)."""
    sample = data[:8192]
    return b"<" in sample or _SPACE_SEPARATED_RE.search(sample) is not None


def extract_candidates(data: bytes, default_type: str, full: bool = False) -> Set[RawCandidate]:
    """Finds proxies in text, HTML tables and JSON.

    Lines with a type:// prefix keep their own type; everything else gets the type of the source.
    For sources of type "auto" the plain lines only count when they are the majority: a generic proxies.txt of
    plain ip:port lines doesn't say its protocol, so they're tried as HTTP and as SOCKS5 (measured on 20,000 such
    entries: 44 worked as http, 32 as socks5, none as both; an unreachable address fails fast for both). In a list
    of mostly prefixed lines, the odd plain one has an unknown type and is left out.
    """
    out: Set[RawCandidate] = set()
    with_scheme = set()
    if b"://" in data:
        for scheme, auth, ip, port in SCHEME_RE.findall(data):
            ptype = SCHEME_TYPES.get(scheme.lower())
            if ptype:
                out.add((ptype, ip, port, auth))
                with_scheme.add((ip, port))
    auto = default_type == "auto"
    regex = PROXY_RE if full or _needs_full_regex(data) else PLAIN_RE  # full: search all of it, not a sample
    pairs = set(regex.findall(data))
    if b'"ip"' in data:
        pairs.update(JSON_IP_PORT_RE.findall(data))
        pairs.update((ip, port) for port, ip in JSON_PORT_IP_RE.findall(data))
    plain = pairs - with_scheme
    # ip:port:user:pass – the bare ip:port stays too: "ip:port:US:elite" has the same shape
    logins = {(ip, port, user + b":" + password) for ip, port, user, password in COLON_LOGIN_RE.findall(data)
              if (ip, port) not in with_scheme}
    if auto and len(plain) <= len(out):
        return out
    for ptype in ("http", "socks5") if auto else (default_type,):
        out.update((ptype, ip, port, b"") for ip, port in plain)
        out.update((ptype, ip, port, auth) for ip, port, auth in logins)
    return out


# networks that aren't publicly reachable (private, loopback, CGNAT, documentation, multicast, reserved …).
# ipaddress.is_private and friends are very slow per address, hence a table by first octet:
# True = the whole /8 is blocked, list = only check these subnets, empty = everything public.
_BLOCKED_BY_FIRST_OCTET: list = [[] for _ in range(256)]
for _net in map(ipaddress.IPv4Network, (
    "0.0.0.0/8", "10.0.0.0/8", "100.64.0.0/10", "127.0.0.0/8", "169.254.0.0/16",
    "172.16.0.0/12", "192.0.0.0/24", "192.0.2.0/24", "192.168.0.0/16", "198.18.0.0/15",
    "198.51.100.0/24", "203.0.113.0/24", "224.0.0.0/4", "240.0.0.0/4",
)):
    _first = int(_net.network_address) >> 24
    if _net.prefixlen <= 8:
        for _o in range(_first, _first + 2 ** (8 - _net.prefixlen)):
            _BLOCKED_BY_FIRST_OCTET[_o] = True
    else:
        _BLOCKED_BY_FIRST_OCTET[_first].append((int(_net.network_address), int(_net.netmask)))


def normalize_public_ip(ip: bytes) -> Optional[str]:
    """'001.2.3.4' -> '1.2.3.4'; None for invalid or non-public addresses."""
    a, b, c, d = map(int, ip.split(b"."))
    if a > 255 or b > 255 or c > 255 or d > 255:
        return None
    rules = _BLOCKED_BY_FIRST_OCTET[a]
    if rules is True:
        return None
    if rules:
        n = a << 24 | b << 16 | c << 8 | d
        if any(n & mask == net for net, mask in rules):
            return None
    return f"{a}.{b}.{c}.{d}"


def normalize_proxy(ip: bytes, port: bytes) -> Optional[str]:
    """'001.2.3.4', b'080' -> '1.2.3.4:80'; None for an invalid port or a non-public IP."""
    p = int(port)
    if not 0 < p < 65536:
        return None
    ip_s = normalize_public_ip(ip)
    return f"{ip_s}:{p}" if ip_s else None


def make_key(ptype: str, proxy: str) -> str:
    return f"{ptype} {proxy}"


def split_key(key: str) -> Tuple[str, str]:
    ptype, _, proxy = key.partition(" ")
    return ptype, proxy


def normalize_auth(auth: str) -> str:
    """'user:p%40ss' or 'user:p@ss' -> encoded uniformly ('user:p%40ss'); '' without a user."""
    user, _, password = auth.partition(":")
    return format_auth(unquote(user), unquote(password))


def validate_candidates(candidates: Iterable[RawCandidate]) -> Set[str]:
    """{(type, ip, port, auth)} -> {"type [auth@]ip:port"} only for valid, public addresses."""
    out = set()
    for ptype, ip, port, auth in candidates:
        proxy = normalize_proxy(ip, port)
        if not proxy:
            continue
        if auth:
            creds = normalize_auth(auth.decode("utf-8", "replace"))
            if creds:
                proxy = f"{creds}@{proxy}"
        out.add(make_key(ptype, proxy))
    return out


def parse_blob(data: bytes, default_type: str, wanted: Tuple[str, ...], full: bool = False) -> str:
    """Complete parse step of a source for the process pool.

    Returns the keys as a single string separated by \\n – one object can be passed
    between processes much faster than hundreds of thousands of small ones.
    """
    candidates = extract_candidates(data, default_type, full)
    keys = [k for k in validate_candidates(candidates) if k.split(" ", 1)[0] in wanted]
    return "\n".join(keys)


_ASCII_NUMBER = re.compile(r"[0-9]+")


def parse_proxy_line(line: str, default_type: Optional[str] = None) -> Optional[str]:
    """A line from a result file ('socks5://user:pass@1.2.3.4:1080' or '1.2.3.4:80') -> key."""
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    ptype = default_type
    if "://" in line:
        scheme, _, line = line.partition("://")
        ptype = TYPE_ALIASES.get(scheme.lower())
    if ptype not in PROXY_TYPES:
        return None
    parts = line.split()
    if not parts:  # "http://" with nothing after it
        return None
    line = parts[0]
    colon_login = _COLON_LOGIN_LINE.fullmatch(line)
    if colon_login:  # ip:port:user:pass (#254)
        line, auth = colon_login.group(1), f"{colon_login.group(2)}:{colon_login.group(3)}"
    else:
        auth, _, line = line.rpartition("@")
    ip, _, port = line.partition(":")
    port = port.rstrip("/")
    # ASCII digits only: "²" and other Unicode digits pass str.isdigit(), but int() can't read them
    octets = ip.split(".")
    if not _ASCII_NUMBER.fullmatch(port) or len(octets) != 4 or not all(map(_ASCII_NUMBER.fullmatch, octets)):
        return None
    proxy = normalize_proxy(ip.encode(), port.encode())
    if not proxy:
        return None
    creds = normalize_auth(auth) if auth else ""
    return make_key(ptype, f"{creds}@{proxy}" if creds else proxy)


def parse_keys(lines: Iterable[str], default_type: Optional[str] = None) -> List[str]:
    seen, out = set(), []
    for line in lines:
        key = parse_proxy_line(line, default_type)
        if key and key not in seen:
            seen.add(key)
            out.append(key)
    return out
