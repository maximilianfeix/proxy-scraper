"""Zielseiten für --target: Ein Proxy zählt nur, wenn er diese Seiten wirklich erreicht."""

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
        """Host-Header: mit Port, wenn er vom Standard abweicht – sonst landet man evtl. im falschen vHost."""
        return self.host if self.port == (443 if self.tls else 80) else f"{self.host}:{self.port}"

    @property
    def label(self) -> str:
        """Kurzname für Anzeigen: https://www.google.com/ -> google.com"""
        host = self.host[4:] if self.host.startswith("www.") else self.host
        default = 443 if self.tls else 80
        return host if self.port == default else f"{host}:{self.port}"


def parse_target(text: str) -> Target:
    """'google.com' -> https://google.com/ ; wirft ValueError bei Unbrauchbarem."""
    text = text.strip()
    if "://" not in text:
        text = "https://" + text
    u = urlsplit(text)
    if u.scheme not in ("http", "https"):
        raise ValueError(f"nur http:// und https:// möglich, nicht {u.scheme}://")
    if not u.hostname:
        raise ValueError(f"kein Host in {text!r}")
    tls = u.scheme == "https"
    try:
        port = u.port
    except ValueError as e:  # Port außerhalb 0–65535 o. ä.
        raise ValueError(f"ungültiger Port in {text!r}") from e
    if port is None:
        port = 443 if tls else 80
    elif port <= 0:  # ":0" nicht still durch den Standard-Port ersetzen
        raise ValueError(f"ungültiger Port in {text!r}")
    path = (u.path or "/") + (f"?{u.query}" if u.query else "")
    default = 443 if tls else 80
    netloc = u.hostname if port == default else f"{u.hostname}:{port}"
    return Target(url=f"{u.scheme}://{netloc}{path}", host=u.hostname, port=port, path=path, tls=tls)


def target_label(url: str) -> str:
    try:
        return parse_target(url).label
    except ValueError:
        return url


# Vorschläge für den Einrichtungsassistenten
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
