"""Lokaler rotierender Proxy-Server (--serve).

  pool.py      welche Proxys es gibt und welcher als nächster drankommt
  http.py      HTTP-Anfragen zerlegen/umbauen, Antworten der Upstreams prüfen
  upstream.py  Verbindung über einen Proxy aus dem Pool aufbauen
  core.py      der Server selbst: Clients annehmen, weiterleiten, bei Fehlern wechseln
"""

from .core import FIRST_CHUNK_WAIT, MAX_ATTEMPTS, MAX_REPLAY_BODY, RequestLog, RotatingServer, ServerStats
from .http import (
    PROXY_AUTH_REQUIRED,
    SCREEN_LIMIT,
    ResponseScreen,
    forward_request,
    origin_request,
    parse_request_head,
    plausible_answer,
)
from .pool import DISABLE_AFTER, PoolEntry, ProxyPool
from .upstream import UpstreamError, open_upstream

__all__ = [
    "DISABLE_AFTER",
    "FIRST_CHUNK_WAIT",
    "MAX_ATTEMPTS",
    "MAX_REPLAY_BODY",
    "PROXY_AUTH_REQUIRED",
    "SCREEN_LIMIT",
    "PoolEntry",
    "ProxyPool",
    "RequestLog",
    "ResponseScreen",
    "RotatingServer",
    "ServerStats",
    "UpstreamError",
    "forward_request",
    "open_upstream",
    "origin_request",
    "parse_request_head",
    "plausible_answer",
]
