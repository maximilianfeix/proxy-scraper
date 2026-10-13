"""One vocabulary for the outcome of every check: what ran, how it ended, when, and against what.

A check ends in exactly one of four states:

  passed       it ran and the proxy did what was asked
  failed       it ran, the target was fine, and the proxy did not do what was asked
  unavailable  it could not run or says nothing about the proxy: the target didn't answer directly either,
               there was no reference to compare with, or this machine ran out of sockets
  skipped      it was left out on purpose (--fast, a filter already ruled the proxy out, an earlier step failed)

"Not run" is never reported as "passed", and an outage of a check target is never reported as a failure of
the proxies checked against it. A failed check is a measurement, not a verdict about the operator: a different
exit IP on the second request can be a rotating pool, a changed page can be an ad network or a captive portal.
"""

from __future__ import annotations

import asyncio
import errno
import ssl
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Optional

PASSED = "passed"
FAILED = "failed"
UNAVAILABLE = "unavailable"
SKIPPED = "skipped"
STATES = (PASSED, FAILED, UNAVAILABLE, SKIPPED)

# the checks of one proxy, in the order they run
BASIC = "basic"      # handshake + a first request: a public exit IP that isn't ours
CONFIRM = "confirm"  # a second request to an unrelated site: the same exit IP again
CONTENT = "content"  # a known static page has to arrive byte for byte
HTTPS = "https"      # a tunnel to port 443 with a verified TLS handshake inside
CHECKS = (BASIC, CONFIRM, CONTENT, HTTPS)

# reason code -> what it means, in words (the diagnosis prints these, docs/check-states.md lists them)
REASONS: Dict[str, str] = {
    # the proxy itself
    "connect_timeout": "no TCP connection to the proxy within the time limit",
    "connect_refused": "the proxy's port refused the connection",
    "connect_failed": "the proxy's address could not be reached",
    "known_unreachable": "this address already failed to connect earlier in the same run",
    "handshake_refused": "the proxy answered, but refused the handshake or the connection to the target",
    "timeout": "the proxy accepted the connection but did not answer in time",
    "connection_closed": "the proxy closed the connection before a complete answer",
    "connection_error": "the connection through the proxy broke",
    "bad_status": "the answer through the proxy was not an HTTP 200",
    "invalid_response": "the answer was not what the target sends (wrong format or content)",
    "private_exit_ip": "the exit IP is a private or reserved address – the proxy answered by itself",
    "own_ip_exposed": "the target saw this machine's own IP – the proxy does not hide it",
    "exit_ip_mismatch": "the second site saw a different exit IP than the first",
    "content_mismatch": "the static test page arrived with different bytes than the reference",
    "tunnel_refused": "the proxy did not open a tunnel to port 443",
    "tls_certificate_invalid": "the certificate inside the tunnel did not verify",
    "tls_error": "the TLS handshake inside the tunnel failed",
    # nothing learned about the proxy
    "target_not_configured": "the check target did not answer when this run started, so the check never ran",
    "target_unreachable": "the check target did not answer directly either while this was checked",
    "no_reference": "there was no reference page to compare with",
    "local_resource_limit": "this machine ran out of sockets or file descriptors",
    # left out on purpose
    "fast_mode": "left out with --fast",
    "filtered_out": "a filter had already ruled this proxy out",
    "earlier_check_failed": "an earlier check did not pass, so this one did not run",
    "cancelled": "the run stopped before this check",
}

LOCAL_ERRNOS = {errno.EMFILE, errno.ENFILE, errno.ENOBUFS, errno.ENOMEM}


class CheckFailed(Exception):
    """A check ended with a known reason code (see REASONS)."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def now_iso() -> str:
    """The time a check finished: ISO 8601, UTC, to the second."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Check:
    state: str
    reason: str = ""             # a code from REASONS, empty for "passed"
    target: str = ""             # what was contacted through the proxy, e.g. "httpbin.org:80"
    at: str = ""                 # when it finished (ISO 8601, UTC)
    ms: Optional[int] = None     # how long it took
    data: Dict[str, object] = field(default_factory=dict)  # what was measured (exit IP, sizes, …)
    limits: str = ""             # what this result does not say

    @property
    def ok(self) -> bool:
        return self.state == PASSED

    def as_dict(self) -> dict:
        """For JSON: the state always, everything else only when it says something."""
        out: Dict[str, object] = {"state": self.state}
        for name in ("reason", "target", "at", "ms", "data", "limits"):
            value = getattr(self, name)
            if value not in ("", None, {}):
                out[name] = value
        return out

    @classmethod
    def from_dict(cls, raw: object) -> Optional["Check"]:
        """A check from published JSON; None for anything that isn't one (lists come from the network)."""
        if not isinstance(raw, dict) or raw.get("state") not in STATES:
            return None
        ms, data = raw.get("ms"), raw.get("data")
        return cls(state=raw["state"], reason=str(raw.get("reason") or ""), target=str(raw.get("target") or ""),
                   at=str(raw.get("at") or ""), ms=ms if type(ms) is int else None,
                   data=dict(data) if isinstance(data, dict) else {}, limits=str(raw.get("limits") or ""))

    def label(self) -> str:
        """'passed' or 'failed:exit_ip_mismatch' – one cell in a CSV, one key in a counter."""
        return f"{self.state}:{self.reason}" if self.reason else self.state


def reason_for(error: BaseException) -> str:
    """The reason code for an exception from a connection through a proxy."""
    if isinstance(error, CheckFailed):
        return error.reason
    if isinstance(error, asyncio.TimeoutError):  # before OSError: on Python 3.11+ it is one
        return "timeout"
    if isinstance(error, ssl.SSLCertVerificationError):
        return "tls_certificate_invalid"
    if isinstance(error, ssl.SSLError):
        return "tls_error"
    if isinstance(error, OSError) and error.errno in LOCAL_ERRNOS:
        return "local_resource_limit"
    if isinstance(error, ConnectionRefusedError):
        return "connect_refused"
    if isinstance(error, (asyncio.IncompleteReadError, ConnectionError, EOFError)):
        return "connection_closed"
    if isinstance(error, OSError):
        return "connection_error"
    return "invalid_response"  # a response that couldn't be parsed (ValueError, LimitOverrunError, …)


def state_for(reason: str) -> str:
    """Our own shortage says nothing about the proxy; every other reason here is the proxy's."""
    return UNAVAILABLE if reason == "local_resource_limit" else FAILED


def legacy_bool(check: Optional[Check]) -> Optional[bool]:
    """The old three-valued field (https: true/false/null) from a check: null for anything not measured."""
    if check is None or check.state in (UNAVAILABLE, SKIPPED):
        return None
    return check.state == PASSED
