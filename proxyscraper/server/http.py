"""HTTP on the client and the upstream side: take requests apart and rebuild them, check responses."""

from __future__ import annotations

import re
from typing import List, Tuple

TLS_HANDSHAKE, TLS_ALERT = b"\x16", b"\x15"  # first byte of a TLS record
HOP_BY_HOP = {b"proxy-connection", b"connection", b"keep-alive", b"proxy-authorization", b"te", b"upgrade"}
PROXY_AUTH_REQUIRED = re.compile(rb"HTTP/1\.[01] 407\b")
STATUS_LEN = len(b"HTTP/1.1 407 ")
STATUS_RE = re.compile(rb"HTTP/1\.[01] (\d{3})[ \r\n]")  # exactly three digits – "4070" is not a 407
SCREEN_LIMIT = 16384


def parse_request_head(head: bytes) -> Tuple[str, str, int, bytes, List[Tuple[bytes, bytes]]]:
    """-> (method, host, port, path, headers). Supports CONNECT host:port and absolute URLs."""
    lines = head.split(b"\r\n")
    method, target, _version = lines[0].split(b" ", 2)
    headers = []
    for line in lines[1:]:
        if line:
            name, _, value = line.partition(b":")
            headers.append((name.strip(), value.strip()))
    if method == b"CONNECT":
        host, _, port = target.decode("ascii").rpartition(":")
        return "CONNECT", host.strip("[]"), _valid_port(port), b"", headers
    if not target.lower().startswith(b"http://"):
        raise ValueError("only absolute http:// URLs or CONNECT")
    rest = target[7:]
    hostport, slash, path = rest.partition(b"/")
    host, _, port = hostport.decode("ascii").partition(":")
    return method.decode("ascii"), host, _valid_port(port or "80"), b"/" + path if slash else b"/", headers


def _valid_port(text: str) -> int:
    port = int(text)
    if not 0 < port < 65536:
        raise ValueError(f"invalid port {port}")
    return port


def origin_request(method: str, path: bytes, host: str, port: int, headers: List[Tuple[bytes, bytes]]) -> bytes:
    """Request for the target server: path instead of an absolute URL, no proxy headers, one request per connection."""
    lines = [f"{method} ".encode() + path + b" HTTP/1.1"]
    if not any(name.lower() == b"host" for name, _ in headers):
        lines.append(b"Host: " + (host if port == 80 else f"{host}:{port}").encode())
    lines += [name + b": " + value for name, value in headers if name.lower() not in HOP_BY_HOP]
    lines.append(b"Connection: close")
    return b"\r\n".join(lines) + b"\r\n\r\n"


def forward_request(method: str, path: bytes, host: str, port: int, headers: List[Tuple[bytes, bytes]]) -> bytes:
    """Request to an HTTP upstream proxy: absolute URL as sent by the client, just without proxy headers."""
    authority = host if port == 80 else f"{host}:{port}"
    request = origin_request(method, path, host, port, headers)
    rest = request.split(b"\r\n", 1)[1]  # the first line is replaced by the absolute URL
    return f"{method} http://{authority}".encode() + path + b" HTTP/1.1\r\n" + rest


class ResponseScreen:
    """Checks the start of an upstream response until the final status line is there.

    Interim responses (100 Continue and the like) go to the client right away; if a 407 follows,
    the client should never see it. feed() returns what may already go on, and the decision:
    None = still open, "ok" = just pass everything else through, "407" = the proxy wants a login
    (or sends an implausibly long interim response – both mean: don't use this upstream)."""

    def __init__(self):
        self.buf = b""

    def feed(self, data: bytes):
        self.buf += data
        out = b""
        while True:
            head = self.buf
            if len(head) < STATUS_LEN and b"\n" not in head and head[:5] == b"HTTP/"[:len(head[:5])]:
                return out, None  # status line still incomplete
            m = STATUS_RE.match(head)
            if not m:
                return out + self._flush(), "ok"  # not an HTTP response (e.g. a tunnel) – nothing to check
            code = m.group(1)
            if code == b"407":
                return out, "407"
            if not code.startswith(b"1") or code == b"101":  # 101 Switching Protocols is final
                return out + self._flush(), "ok"
            end = head.find(b"\r\n\r\n")
            if end < 0:
                if len(head) > SCREEN_LIMIT:
                    return out, "407"  # huge interim response – better count it as failed than let it through blindly
                return out, None  # interim response not complete yet
            out += head[:end + 4]
            self.buf = head[end + 4:]
            if not self.buf:
                return out, None

    def _flush(self) -> bytes:
        data, self.buf = self.buf, b""
        return data


def plausible_answer(first_out: bytes, first_in: bytes) -> bool:
    """Does the first response fit the request? If the client starts with a TLS handshake (0x16), the
    other side has to speak TLS too – some proxies send an HTTP error page inside the tunnel instead.
    A 407 always comes from the proxy itself (login missing or wrong), never from the target site."""
    if first_out[:1] == TLS_HANDSHAKE:
        return first_in[:1] in (TLS_HANDSHAKE, TLS_ALERT)
    return not PROXY_AUTH_REQUIRED.match(first_in)
