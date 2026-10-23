"""Which addresses an HTTP request may reach – for URLs nobody chose by hand.

Sources found automatically (URLs mined from other scrapers' configs, lists named by third-party meta lists)
come from files anyone can write. Fetching them with the public-only policy keeps such a file from pointing the
scraper at localhost, the local network or a cloud metadata service:

- scheme and port are checked for the URL and for every redirect hop,
- IP literals are recognized in every spelling the system resolver accepts (127.1, 0x7f.1, 2130706433,
  0177.0.0.1, IPv4-mapped/-compatible IPv6, NAT64, 6to4, Teredo) and must be public,
- names are resolved once, every answer must be public, and the connection then goes to one of exactly
  those addresses (no second lookup an attacker's DNS could answer differently). Host header, TLS SNI and
  certificate check stay on the name.

Requests without a policy (curated sources, own --source URLs, APIs) are not restricted. Private addresses
are only reachable through a separate, explicit policy (allow_networks), e.g. in tests.
"""

from __future__ import annotations

import asyncio
import ipaddress
import re
import socket
from dataclasses import dataclass
from typing import FrozenSet, List, Optional, Tuple, Union
from urllib.parse import urlsplit

IPAddress = Union[ipaddress.IPv4Address, ipaddress.IPv6Address]
IPNetwork = Union[ipaddress.IPv4Network, ipaddress.IPv6Network]


class BlockedTarget(ConnectionError):
    """The URL points somewhere the policy doesn't allow (non-public address, scheme, port)."""


# networks that ipaddress doesn't (in every supported Python version) count as non-global
_NOT_PUBLIC = tuple(ipaddress.ip_network(n) for n in (
    "100.64.0.0/10",    # CGNAT (is_private is False for it)
    "192.88.99.0/24",   # 6to4 relay anycast (deprecated)
    "64:ff9b:1::/48",   # NAT64 local use (only private in Python >= 3.13)
))
_NAT64 = ipaddress.ip_network("64:ff9b::/96")
_TEREDO = ipaddress.ip_network("2001::/32")
_IPV4_COMPAT = ipaddress.ip_network("::/96")


def is_public_address(ip: IPAddress) -> bool:
    """Globally reachable unicast. Not: loopback, private, link-local, CGNAT, multicast, reserved,
    unspecified, documentation/benchmark ranges – also not when wrapped in an IPv6 address."""
    if isinstance(ip, ipaddress.IPv6Address):
        if getattr(ip, "scope_id", None):
            return False
        if ip.ipv4_mapped is not None:
            return is_public_address(ip.ipv4_mapped)
        embedded = None
        if ip in _NAT64 or ip in _IPV4_COMPAT:
            embedded = ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
        elif ip.sixtofour is not None:
            embedded = ip.sixtofour
        elif ip in _TEREDO and ip.teredo is not None:
            embedded = ip.teredo[1]
        if embedded is not None and not is_public_address(embedded):
            return False
        if ip in _NAT64:
            return True  # the well-known NAT64 prefix in front of a public IPv4
        if ip.is_site_local:
            return False
    # is_global alone isn't enough: before 3.11/3.13 it is True for multicast and some reserved ranges
    return (ip.is_global and not ip.is_multicast and not ip.is_reserved and not ip.is_loopback
            and not ip.is_link_local and not ip.is_unspecified and not ip.is_private
            and not any(ip in net for net in _NOT_PUBLIC if net.version == ip.version))


_NUMERIC_PART_RE = re.compile(r"0[xX][0-9a-fA-F]*|[0-9]+")


def parse_ip_literal(host: str) -> Optional[IPAddress]:
    """The address a host stands for if it is an IP literal (in any spelling inet_aton/getaddrinfo accept),
    None for a name. Raises BlockedTarget for numeric hosts that are no valid address – those must not be
    handed to a resolver that might read them differently."""
    host = host.strip()
    if host.startswith("[") and host.endswith("]"):
        host = host[1:-1]
    if "%" in host:  # IPv6 zone id: only meaningful on a local link
        raise BlockedTarget(f"scoped address: {host}")
    if ":" in host:
        try:
            return ipaddress.IPv6Address(host)
        except ValueError:
            raise BlockedTarget(f"invalid address: {host}") from None
    host = host[:-1] if host.endswith(".") else host
    parts = host.split(".")
    if not host or not all(_NUMERIC_PART_RE.fullmatch(p) for p in parts):
        return None  # a name (at least one label isn't a number)
    if len(parts) > 4:
        raise BlockedTarget(f"invalid address: {host}")
    values = []
    for p in parts:
        if p[:2].lower() == "0x":
            values.append(int(p[2:] or "0", 16))
        elif len(p) > 1 and p.startswith("0"):
            if not set(p) <= set("01234567"):
                raise BlockedTarget(f"invalid address: {host}")
            values.append(int(p, 8))
        else:
            values.append(int(p))
    # a.b.c.d / a.b.c (c: 16 bit) / a.b (b: 24 bit) / a (32 bit) – like inet_aton
    *head, last = values
    if any(v > 255 for v in head) or last >= 256 ** (5 - len(values)):
        raise BlockedTarget(f"invalid address: {host}")
    number = 0
    for v in head:
        number = number * 256 + v
    number = (number << (8 * (5 - len(values)))) | last
    return ipaddress.IPv4Address(number)


@dataclass(frozen=True)
class Target:
    host: str            # for Host header, SNI and certificate check
    port: int
    https: bool
    addresses: List[str]  # checked; the connection goes to one of these


@dataclass(frozen=True)
class TargetPolicy:
    """Public addresses only; ports=None allows any port. allow_networks: an explicit exception for
    non-public networks (tests, a deliberately configured private mirror) – never the default."""
    schemes: Tuple[str, ...] = ("http", "https")
    ports: Optional[FrozenSet[int]] = frozenset({80, 443})
    allow_networks: Tuple[IPNetwork, ...] = ()
    resolve_timeout: float = 10.0

    def allows(self, ip: IPAddress) -> bool:
        if any(ip.version == net.version and ip in net for net in self.allow_networks):
            return True
        return is_public_address(ip)

    async def resolve(self, url: str) -> Target:
        """Checks scheme, port and every address the host stands for -> Target, or BlockedTarget."""
        try:
            parts = urlsplit(url)
            port = parts.port
        except ValueError:
            raise BlockedTarget(f"invalid URL: {url!r}") from None
        if parts.scheme not in self.schemes:
            raise BlockedTarget(f"scheme not allowed: {parts.scheme!r}")
        https = parts.scheme == "https"
        port = port or (443 if https else 80)
        if self.ports is not None and port not in self.ports:
            raise BlockedTarget(f"port not allowed: {port}")
        host = parts.hostname or ""
        if not host:
            raise BlockedTarget(f"no host in {url!r}")
        literal = parse_ip_literal(host)
        if literal is not None:
            ips: List[IPAddress] = [literal]
        else:
            infos = await asyncio.wait_for(
                asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM), self.resolve_timeout)
            ips = []
            for info in infos:
                try:
                    ip = ipaddress.ip_address(info[4][0])
                except ValueError:  # e.g. a scoped fe80::1%en0
                    raise BlockedTarget(f"{host} resolves to {info[4][0]}") from None
                if ip not in ips:
                    ips.append(ip)
        if not ips:
            raise BlockedTarget(f"{host} has no address")
        for ip in ips:  # one non-public answer is enough to refuse: no mixing in an internal address
            if not self.allows(ip):
                raise BlockedTarget(f"{host} resolves to a non-public address ({ip})")
        return Target(host, port, https, [str(ip) for ip in ips])


PUBLIC_ONLY = TargetPolicy()
