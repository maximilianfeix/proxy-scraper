"""HTTP auf der Client- und der Upstream-Seite: Anfragen zerlegen und umbauen, Antworten prüfen."""

from __future__ import annotations

import re
from typing import List, Tuple

TLS_HANDSHAKE, TLS_ALERT = b"\x16", b"\x15"  # erstes Byte eines TLS-Records
HOP_BY_HOP = {b"proxy-connection", b"connection", b"keep-alive", b"proxy-authorization", b"te", b"upgrade"}
PROXY_AUTH_REQUIRED = re.compile(rb"HTTP/1\.[01] 407\b")
STATUS_LEN = len(b"HTTP/1.1 407 ")
STATUS_RE = re.compile(rb"HTTP/1\.[01] (\d{3})[ \r\n]")  # genau drei Ziffern – "4070" ist kein 407
SCREEN_LIMIT = 16384


def parse_request_head(head: bytes) -> Tuple[str, str, int, bytes, List[Tuple[bytes, bytes]]]:
    """-> (Methode, Host, Port, Pfad, Header). Unterstützt CONNECT host:port und absolute URLs."""
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
        raise ValueError("nur absolute http://-URLs oder CONNECT")
    rest = target[7:]
    hostport, slash, path = rest.partition(b"/")
    host, _, port = hostport.decode("ascii").partition(":")
    return method.decode("ascii"), host, _valid_port(port or "80"), b"/" + path if slash else b"/", headers


def _valid_port(text: str) -> int:
    port = int(text)
    if not 0 < port < 65536:
        raise ValueError(f"ungültiger Port {port}")
    return port


def origin_request(method: str, path: bytes, host: str, port: int, headers: List[Tuple[bytes, bytes]]) -> bytes:
    """Anfrage für den Zielserver: Pfad statt absoluter URL, ohne Proxy-Header, eine Anfrage pro Verbindung."""
    lines = [f"{method} ".encode() + path + b" HTTP/1.1"]
    if not any(name.lower() == b"host" for name, _ in headers):
        lines.append(b"Host: " + (host if port == 80 else f"{host}:{port}").encode())
    lines += [name + b": " + value for name, value in headers if name.lower() not in HOP_BY_HOP]
    lines.append(b"Connection: close")
    return b"\r\n".join(lines) + b"\r\n\r\n"


def forward_request(method: str, path: bytes, host: str, port: int, headers: List[Tuple[bytes, bytes]]) -> bytes:
    """Anfrage an einen HTTP-Upstream-Proxy: absolute URL wie vom Client, nur ohne Proxy-Header."""
    authority = host if port == 80 else f"{host}:{port}"
    request = origin_request(method, path, host, port, headers)
    rest = request.split(b"\r\n", 1)[1]  # erste Zeile wird durch die absolute URL ersetzt
    return f"{method} http://{authority}".encode() + path + b" HTTP/1.1\r\n" + rest


class ResponseScreen:
    """Prüft den Anfang einer Upstream-Antwort, bis die endgültige Statuszeile da ist.

    Zwischenantworten (100 Continue & Co.) gehen sofort an den Client weiter; kommt danach ein 407,
    soll der Client das nie sehen. feed() gibt zurück, was schon weiter darf, und die Entscheidung:
    None = noch offen, "ok" = alles Weitere einfach durchreichen, "407" = Proxy will einen Login
    (oder schickt eine unplausibel lange Zwischenantwort – beides heißt: diesen Upstream nicht nehmen)."""

    def __init__(self):
        self.buf = b""

    def feed(self, data: bytes):
        self.buf += data
        out = b""
        while True:
            head = self.buf
            if len(head) < STATUS_LEN and b"\n" not in head and head[:5] == b"HTTP/"[:len(head[:5])]:
                return out, None  # Statuszeile noch unvollständig
            m = STATUS_RE.match(head)
            if not m:
                return out + self._flush(), "ok"  # keine HTTP-Antwort (z. B. Tunnel) – nichts zu prüfen
            code = m.group(1)
            if code == b"407":
                return out, "407"
            if not code.startswith(b"1") or code == b"101":  # 101 Switching Protocols ist endgültig
                return out + self._flush(), "ok"
            end = head.find(b"\r\n\r\n")
            if end < 0:
                if len(head) > SCREEN_LIMIT:
                    return out, "407"  # riesige Zwischenantwort – lieber als gescheitert werten als blind durchlassen
                return out, None  # Zwischenantwort noch nicht vollständig
            out += head[:end + 4]
            self.buf = head[end + 4:]
            if not self.buf:
                return out, None

    def _flush(self) -> bytes:
        data, self.buf = self.buf, b""
        return data


def plausible_answer(first_out: bytes, first_in: bytes) -> bool:
    """Passt die erste Antwort zur Anfrage? Beginnt der Client mit einem TLS-Handshake (0x16), muss die
    Gegenseite auch TLS sprechen – manche Proxys schicken im Tunnel stattdessen eine HTTP-Fehlerseite.
    Ein 407 kommt immer vom Proxy selbst (Login fehlt oder falsch), nie von der Zielseite."""
    if first_out[:1] == TLS_HANDSHAKE:
        return first_in[:1] in (TLS_HANDSHAKE, TLS_ALERT)
    return not PROXY_AUTH_REQUIRED.match(first_in)
