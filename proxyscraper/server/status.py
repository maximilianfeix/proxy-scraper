"""Status als JSON unter http://127.0.0.1:PORT/__proxy-scraper/status und Wünsche aus der Proxy-Anmeldung."""

from __future__ import annotations

import base64
import binascii
import json
import time
from typing import Any, List, Tuple

from ..ui.widgets import shown_proxy
from .pool import Selection

STATUS_PREFIX = b"GET /__proxy-scraper/"


def selection_from_headers(headers: List[Tuple[bytes, bytes]]) -> Selection:
    """Proxy-Authorization: Basic base64("country-de-session-abc:beliebig") -> Selection."""
    for name, value in headers:
        if name.lower() == b"proxy-authorization" and value[:6].lower() == b"basic ":
            try:
                user = base64.b64decode(value[6:].strip(), validate=True).decode("utf-8", "replace")
            except (binascii.Error, ValueError):
                return Selection()
            return Selection.from_username(user.partition(":")[0])
    return Selection()


def status_json(server: Any) -> str:
    """server: der RotatingServer (nicht importiert, sonst hingen core und status im Kreis voneinander ab)."""
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
                 "revived": server.revived},
        "proxies": [
            {"url": f"{e.result.ptype}://{shown_proxy(e.result.proxy)}", "country": e.result.country,
             "latency_ms": e.result.latency, "https": e.result.https, "ok": e.ok, "fail": e.fail,
             "disabled": e.disabled, "active": e.active}
            for e in entries[:100]
        ],
    }
    return json.dumps(payload, indent=1, ensure_ascii=False)
