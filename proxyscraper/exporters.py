"""Zusatzformate für gängige Tools (--export).

  proxychains   proxychains.conf mit random_chain – direkt nutzbar mit `proxychains4 -f`
  clash         clash.yaml für Clash / Mihomo: Proxys plus eine url-test-Gruppe
                (beide ohne HTTP-Proxys, die kein CONNECT können, siehe tunnels())
  curl          curl.txt, eine URL pro Zeile im Format für `curl -x` (SOCKS5 mit DNS über den Proxy)
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Callable, Dict, List, Sequence, Tuple

from .checker import CheckResult
from .handshake import parse_endpoint

Exporter = Callable[[Sequence[CheckResult], datetime], str]




def tunnels(r: CheckResult) -> bool:
    """proxychains und Clash reden mit HTTP-Proxys nur per CONNECT. Wer den HTTPS-Test nicht
    bestanden hat, kann das in der Regel nicht – SOCKS geht immer, ungetestet (--fast) bleibt drin."""
    return r.ptype != "http" or r.https is not False


def proxychains(rows: Sequence[CheckResult], now: datetime) -> str:
    entries = []
    for r in rows:
        ep = parse_endpoint(r.proxy)
        creds = [ep.user, ep.password] if ep.has_auth else []
        if not tunnels(r) or any(not c or c.split() != [c] for c in creds):
            continue  # proxychains trennt an Leerzeichen, leere Felder gehen auch nicht
        entries.append(" ".join([r.ptype, ep.host, str(ep.port), *creds]))
    lines = [
        f"# proxy-scraper, {now:%Y-%m-%d %H:%M}, {len(entries)} Proxys (schnellste zuerst, HTTP nur mit CONNECT)",
        "# Nutzung: proxychains4 -f proxychains.conf curl https://api.ipify.org",
        "random_chain",
        "chain_len = 1",
        "proxy_dns",
        "tcp_read_time_out 15000",
        "tcp_connect_time_out 8000",
        "",
        "[ProxyList]",
    ]
    return "\n".join(lines + entries) + "\n"


CLASH_TYPES = {"http": "http", "socks5": "socks5"}  # SOCKS4 kennt Clash nicht


def clash(rows: Sequence[CheckResult], now: datetime) -> str:
    # JSON-Strings sind gültiges YAML – so braucht es keine YAML-Bibliothek und nichts muss escaped werden
    q = json.dumps
    usable = [r for r in rows if r.ptype in CLASH_TYPES and tunnels(r)]
    names: List[str] = []
    taken = set()
    lines = [f"# proxy-scraper, {now:%Y-%m-%d %H:%M}, {len(usable)} Proxys (SOCKS4 kann Clash nicht)", "proxies:"]
    for r in usable:
        ep = parse_endpoint(r.proxy)
        base = name = f"{r.country or '??'} {r.ptype} {ep.address}"
        n = 1
        while name in taken:  # derselbe Proxy mit verschiedenen Zugangsdaten
            n += 1
            name = f"{base} #{n}"
        taken.add(name)
        names.append(name)
        lines += [
            f"  - name: {q(name)}",
            f"    type: {CLASH_TYPES[r.ptype]}",
            f"    server: {q(ep.host)}",
            f"    port: {ep.port}",
        ]
        if ep.has_auth:
            lines += [f"    username: {q(ep.user)}", f"    password: {q(ep.password)}"]
        if r.ptype == "socks5":
            lines.append("    udp: false")
    if not usable:
        lines[-1] = "proxies: []"
        return "\n".join(lines) + "\n"
    lines += [
        "proxy-groups:",
        "  - name: proxy-scraper",
        "    type: url-test",
        "    url: http://www.gstatic.com/generate_204",
        "    interval: 300",
        "    tolerance: 100",
        "    proxies:",
        *(f"      - {q(n)}" for n in names),
        "rules:",
        "  - MATCH,proxy-scraper",
    ]
    return "\n".join(lines) + "\n"


CURL_SCHEMES = {"socks5": "socks5h", "socks4": "socks4", "http": "http"}


def curl(rows: Sequence[CheckResult], now: datetime) -> str:
    return "".join(f"{CURL_SCHEMES[r.ptype]}://{r.proxy}\n" for r in rows)


EXPORTERS: Dict[str, Tuple[str, Exporter]] = {
    "proxychains": ("proxychains.conf", proxychains),
    "clash": ("clash.yaml", clash),
    "curl": ("curl.txt", curl),
}


def parse_exports(value: str) -> List[str]:
    """"clash,curl" -> ["clash", "curl"]; "all" -> alle. Unbekannte Namen -> ValueError."""
    names = [n.strip().lower() for n in value.split(",") if n.strip()]
    unknown = [n for n in names if n not in EXPORTERS and n != "all"]
    if unknown:  # vor "all" prüfen – sonst ginge ein Tippfehler in "all,clsh" still unter
        raise ValueError(f"unbekanntes Format: {', '.join(unknown)} (möglich: {', '.join(EXPORTERS)}, all)")
    if "all" in names:
        return list(EXPORTERS)
    return [n for n in EXPORTERS if n in names]  # feste Reihenfolge, keine Duplikate
