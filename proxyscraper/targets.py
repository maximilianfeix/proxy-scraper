"""Target sites for --target: a proxy only counts if it really reaches these sites."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Target:
    url: str
    host: str
    port: int
    path: str
    tls: bool

    @property
    def host_header(self) -> str:
        """Host header: with the port if it differs from the default – otherwise you may end up in the wrong vhost."""
        return self.host if self.port == (443 if self.tls else 80) else f"{self.host}:{self.port}"

    @property
    def label(self) -> str:
        """Short name for display: https://www.google.com/ -> google.com"""
        host = self.host[4:] if self.host.startswith("www.") else self.host
        default = 443 if self.tls else 80
        return host if self.port == default else f"{host}:{self.port}"


def parse_target(text: str) -> Target:
    """'google.com' -> https://google.com/ ; raises ValueError for anything unusable."""
    text = text.strip()
    if "://" not in text:
        text = "https://" + text
    u = urlsplit(text)
    if u.scheme not in ("http", "https"):
        raise ValueError(f"only http:// and https:// are possible, not {u.scheme}://")
    if not u.hostname:
        raise ValueError(f"no host in {text!r}")
    tls = u.scheme == "https"
    try:
        port = u.port
    except ValueError as e:  # port outside 0–65535 or similar
        raise ValueError(f"invalid port in {text!r}") from e
    if port is None:
        port = 443 if tls else 80
    elif port <= 0:  # don't silently replace ":0" with the default port
        raise ValueError(f"invalid port in {text!r}")
    path = (u.path or "/") + (f"?{u.query}" if u.query else "")
    default = 443 if tls else 80
    netloc = u.hostname if port == default else f"{u.hostname}:{port}"
    return Target(url=f"{u.scheme}://{netloc}{path}", host=u.hostname, port=port, path=path, tls=tls)


def target_label(url: str, others=()) -> str:
    """Short name; with the scheme when it could be confused (http:// and https:// of the same site)."""
    try:
        label = parse_target(url).label
    except ValueError:
        return url
    if any(o != url and target_label(o) == label for o in others):
        return url.split("/", 3)[0] + "//" + label
    return label


# suggestions for the setup wizard
SUGGESTIONS = (
    ("Google", "https://www.google.com/"),
    ("YouTube", "https://www.youtube.com/"),
    ("Discord", "https://discord.com/"),
    ("Instagram", "https://www.instagram.com/"),
    ("X / Twitter", "https://x.com/"),
    ("Reddit", "https://www.reddit.com/"),
    ("TikTok", "https://www.tiktok.com/"),
    ("Amazon", "https://www.amazon.de/"),
)
