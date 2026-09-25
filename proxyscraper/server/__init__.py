"""Local rotating proxy server (--serve).

  pool.py      which proxies there are and which one comes next
  http.py      take HTTP requests apart and rebuild them, check upstream responses
  upstream.py  connect through a proxy from the pool
  core.py      the server itself: accept clients, relay, switch on errors
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
