"""Status as JSON (/__proxy-scraper/status), metrics for Prometheus (/__proxy-scraper/metrics), the live dashboard
(/__proxy-scraper/) and wishes from the proxy login."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import re
import time
from collections import Counter
from pathlib import Path
from statistics import median
from typing import Any, Dict, List, Optional, Tuple

from ..parsing import PROXY_TYPES
from ..ui.widgets import shown_proxy
from .pool import Selection

STATUS_PREFIX = b"GET /__proxy-scraper/"
STATUS_PATH = b"/__proxy-scraper/status"
METRICS_PATH = b"/__proxy-scraper/metrics"
METRICS_TYPE = b"text/plain; version=0.0.4; charset=utf-8"
DASHBOARD_PATHS = (b"/__proxy-scraper/", b"/__proxy-scraper/dashboard")
DASHBOARD_TYPE = b"text/html; charset=utf-8"
DASHBOARD_HTML = (Path(__file__).parent / "dashboard.html").read_bytes()


def _dashboard_headers(page: bytes) -> bytes:
    """A strict CSP: the page's own script (by hash), its inline styles, and fetches to this server only."""
    script = re.search(rb"<script>(.*?)</script>", page, re.S)
    digest = base64.b64encode(hashlib.sha256(script.group(1) if script else b"").digest()).decode()
    csp = (f"default-src 'none'; script-src 'sha256-{digest}'; style-src 'unsafe-inline'; img-src data:; "
           "connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
    return (f"Content-Security-Policy: {csp}\r\n"
            "X-Content-Type-Options: nosniff\r\nReferrer-Policy: no-referrer\r\n").encode()


DASHBOARD_HEADERS = _dashboard_headers(DASHBOARD_HTML)


def basic_credentials(headers: List[Tuple[bytes, bytes]], header: bytes = b"proxy-authorization"
                      ) -> Optional[Tuple[str, str]]:
    """Basic auth from the given header -> (user, password), None if missing or broken."""
    for name, value in headers:
        if name.lower() == header and value[:6].lower() == b"basic ":
            try:
                decoded = base64.b64decode(value[6:].strip(), validate=True).decode("utf-8", "replace")
            except (binascii.Error, ValueError):
                return None
            user, _, password = decoded.partition(":")
            return user, password
    return None


def password_ok(headers: List[Tuple[bytes, bytes]], password: str, header: bytes = b"proxy-authorization") -> bool:
    """No password configured, or the Basic auth in `header` carries exactly this password."""
    if not password:
        return True
    creds = basic_credentials(headers, header)
    return creds is not None and hmac.compare_digest(creds[1].encode(), password.encode())


def selection_from_headers(headers: List[Tuple[bytes, bytes]]) -> Selection:
    """Proxy-Authorization: Basic base64("country-de-session-abc:anything") -> Selection."""
    creds = basic_credentials(headers)
    return Selection.from_username(creds[0]) if creds else Selection()


def status_json(server: Any) -> str:
    """server: the RotatingServer (not imported, otherwise core and status would depend on each other in a circle)."""
    st, pool = server.stats, server.pool
    entries = sorted(pool.entries, key=lambda e: (e.disabled, -e.ok, e.result.latency))
    payload = {
        "listening": f"{server.host}:{server.port}",
        "uptime_seconds": round(time.perf_counter() - st.started),
        "strategy": pool.strategy,
        "sticky_seconds": pool.sticky_seconds,
        "requests": {"total": st.requests, "ok": st.ok, "failed": st.failed, "active": st.active},
        "bytes": {"up": st.bytes_up, "down": st.bytes_down},
        "pool": {"total": len(pool.entries), "usable": len(pool.usable), "https": len(pool.tls_capable),
                 "revived": server.revived, "refilled": server.refilled,
                 "last_refill": server.last_refill and round(server.last_refill)},
        # newest first; who sent a request isn't shown – only where it went and how
        "recent": [{"target": r.target, "via": r.via, "ok": r.ok, "ms": r.ms, "attempts": r.attempts}
                   for r in reversed(st.recent)],
        "countries": dict(Counter(e.result.country for e in pool.entries if not e.disabled and e.result.country)
                          .most_common()),
        "proxies": [
            {"url": f"{e.result.ptype}://{shown_proxy(e.result.proxy)}", "country": e.result.country,
             "latency_ms": e.result.latency, "https": e.result.https, "ok": e.ok, "fail": e.fail,
             "disabled": e.disabled, "active": e.active}
            for e in entries[:100]
        ],
    }
    return json.dumps(payload, indent=1, ensure_ascii=False)


def metrics_text(server: Any) -> str:
    """Prometheus text format, without a dependency – e.g. for Grafana when the server runs permanently."""
    st, pool = server.stats, server.pool
    out: List[str] = []

    def metric(name: str, kind: str, help_text: str, samples: Dict[str, float]) -> None:
        out.append(f"# HELP proxy_scraper_{name} {help_text}")
        out.append(f"# TYPE proxy_scraper_{name} {kind}")
        out.extend(f"proxy_scraper_{name}{labels} {value:g}" for labels, value in samples.items())

    metric("uptime_seconds", "gauge", "Seconds since the server started.",
           {"": round(time.perf_counter() - st.started)})
    metric("requests_total", "counter", "Requests handled, by result.",
           {'{result="ok"}': st.ok, '{result="failed"}': st.failed})
    metric("requests_active", "gauge", "Requests in progress.", {"": st.active})
    metric("bytes_total", "counter", "Bytes relayed, by direction.",
           {'{direction="up"}': st.bytes_up, '{direction="down"}': st.bytes_down})
    metric("revived_total", "counter", "Disabled proxies that passed a re-check.", {"": server.revived})

    proxies, uses, latency = {}, {}, {}
    for t in PROXY_TYPES:
        entries = [e for e in pool.entries if e.result.ptype == t]
        usable = [e for e in entries if not e.disabled]
        proxies[f'{{type="{t}",state="usable"}}'] = len(usable)
        proxies[f'{{type="{t}",state="disabled"}}'] = len(entries) - len(usable)
        uses[f'{{type="{t}",result="ok"}}'] = sum(e.ok for e in entries)
        uses[f'{{type="{t}",result="failed"}}'] = sum(e.fail for e in entries)
        if usable:
            latency[f'{{type="{t}"}}'] = median(e.result.latency for e in usable)
    metric("pool_proxies", "gauge", "Proxies in the pool, by type and state.", proxies)
    metric("proxy_uses_total", "counter", "Upstream attempts, by proxy type and result.", uses)
    metric("pool_latency_median_ms", "gauge", "Median check latency of usable proxies.", latency)
    return "\n".join(out) + "\n"
