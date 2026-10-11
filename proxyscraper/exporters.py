"""Extra formats for common tools (--export).

  proxychains   proxychains.conf with random_chain – ready to use with `proxychains4 -f`
  clash         clash.yaml for Clash / Mihomo: proxies plus a url-test group
                (both without HTTP proxies that can't CONNECT, see tunnels())
  singbox       singbox.json for sing-box: a local mixed (HTTP+SOCKS) inbound on 127.0.0.1:2080 and a
                urltest outbound over every proxy (SOCKS4 too – sing-box can do it)
  curl          curl.txt, one URL per line in the format for `curl -x` (SOCKS5 with DNS through the proxy)
  pac           proxy.pac for browsers, FoxyProxy and the OS proxy settings: the best 30 HTTP and SOCKS5,
                tried in order
  proxifier     proxifier.ppx, a profile for Proxifier 4 on Windows and macOS: the best 50 proxies in a
                redundancy chain (the first that works is used), localhost stays direct
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Callable, Dict, List, Sequence, Tuple

from .checker import CheckResult
from .handshake import parse_endpoint

Exporter = Callable[[Sequence[CheckResult], datetime], str]


def tunnels(r: CheckResult) -> bool:
    """proxychains and Clash only talk to HTTP proxies via CONNECT. Whatever didn't pass the HTTPS test
    usually can't do that – SOCKS always works, untested ones (--fast) stay in."""
    return r.ptype != "http" or r.https is not False


def proxychains(rows: Sequence[CheckResult], now: datetime) -> str:
    entries = []
    for r in rows:
        ep = parse_endpoint(r.proxy)
        creds = [ep.user, ep.password] if ep.has_auth else []
        if not tunnels(r) or any(not c or c.split() != [c] for c in creds):
            continue  # proxychains splits on spaces, empty fields don't work either
        entries.append(" ".join([r.ptype, ep.host, str(ep.port), *creds]))
    lines = [
        f"# proxy-scraper, {now:%Y-%m-%d %H:%M}, {len(entries)} proxies (fastest first, HTTP only with CONNECT)",
        "# usage: proxychains4 -f proxychains.conf curl https://api.ipify.org",
        "random_chain",
        "chain_len = 1",
        "proxy_dns",
        "tcp_read_time_out 15000",
        "tcp_connect_time_out 8000",
        "",
        "[ProxyList]",
    ]
    return "\n".join(lines + entries) + "\n"


CLASH_TYPES = {"http": "http", "socks5": "socks5"}  # Clash doesn't know SOCKS4


def clash(rows: Sequence[CheckResult], now: datetime) -> str:
    # JSON strings are valid YAML – so no YAML library is needed and nothing has to be escaped
    q = json.dumps
    usable = [r for r in rows if r.ptype in CLASH_TYPES and tunnels(r)]
    names: List[str] = []
    taken = set()
    lines = [f"# proxy-scraper, {now:%Y-%m-%d %H:%M}, {len(usable)} proxies (Clash can't do SOCKS4)", "proxies:"]
    for r in usable:
        ep = parse_endpoint(r.proxy)
        base = name = f"{r.country or '??'} {r.ptype} {ep.address}"
        n = 1
        while name in taken:  # the same proxy with different credentials
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


SINGBOX_PORT = 2080


def singbox(rows: Sequence[CheckResult], now: datetime) -> str:
    """sing-box config: `sing-box run -c singbox.json`, then use 127.0.0.1:2080 as HTTP or SOCKS5 proxy."""
    members = []
    taken = set()
    for r in rows:
        if not tunnels(r):
            continue
        ep = parse_endpoint(r.proxy)
        base = tag = f"{r.country or '??'} {r.ptype} {ep.address}"
        n = 1
        while tag in taken:  # the same proxy with different credentials
            n += 1
            tag = f"{base} #{n}"
        taken.add(tag)
        out = {"type": "http" if r.ptype == "http" else "socks", "tag": tag, "server": ep.host,
               "server_port": ep.port}
        if r.ptype != "http":
            out["version"] = "4" if r.ptype == "socks4" else "5"
        if ep.has_auth:
            out["username"] = ep.user
            if r.ptype != "socks4":  # SOCKS4 has no password
                out["password"] = ep.password
        members.append(out)
    outbounds = []
    if members:
        outbounds.append({"type": "urltest", "tag": "proxy-scraper", "outbounds": [m["tag"] for m in members],
                          "url": "https://www.gstatic.com/generate_204", "interval": "5m", "tolerance": 100})
    outbounds += [*members, {"type": "direct", "tag": "direct"}]
    config = {
        "log": {"level": "warn"},
        "inbounds": [{"type": "mixed", "tag": "local", "listen": "127.0.0.1", "listen_port": SINGBOX_PORT}],
        "outbounds": outbounds,
        "route": {"final": "proxy-scraper" if members else "direct"},
    }
    return json.dumps(config, indent=2, ensure_ascii=False) + "\n"


CURL_SCHEMES = {"socks5": "socks5h", "socks4": "socks4", "http": "http"}


def curl(rows: Sequence[CheckResult], now: datetime) -> str:
    return "".join(f"{CURL_SCHEMES[r.ptype]}://{r.proxy}\n" for r in rows)


# SOCKS4 is left out: it can't take a host name, so the browser would look the name up with the user's own DNS
PAC_KEYWORDS = {"http": "PROXY", "socks5": "SOCKS5"}
PAC_MAX = 30  # browsers try the entries in order; more than this only slows down the failure case
PAC_FAIL_CLOSED = "PROXY 127.0.0.1:1"  # nothing listens there – better no page than the real IP
# ES5 only: Windows runs PAC files in an old JScript engine. Local means a local name or a private IPv4
# *address* – "10.attacker.example" is a public site. No isInNet()/dnsResolve(): they'd send every host name
# to the local DNS.
PAC_TEMPLATE = """// proxy-scraper, {when}, {count} proxies, best first.
// The browser tries them in order. Local names and private IPv4 addresses go direct; no DIRECT fallback.
var PROXIES = "{chain}";

function isLocal(host) {{
  if (isPlainHostName(host) || host === "localhost" ||
      shExpMatch(host, "*.localhost") || shExpMatch(host, "*.local")) {{
    return true;
  }}
  var ip = /^(\\d{{1,3}})\\.(\\d{{1,3}})\\.\\d{{1,3}}\\.\\d{{1,3}}$/.exec(host);
  if (!ip) {{
    return false;
  }}
  var a = parseInt(ip[1], 10), b = parseInt(ip[2], 10);
  return a === 127 || a === 10 || (a === 192 && b === 168) || (a === 169 && b === 254) ||
    (a === 172 && b >= 16 && b <= 31);
}}

function FindProxyForURL(url, host) {{
  return isLocal(host) ? "DIRECT" : PROXIES;
}}
"""


def pac(rows: Sequence[CheckResult], now: datetime) -> str:
    entries = []
    for r in rows:
        ep = parse_endpoint(r.proxy)
        if r.ptype not in PAC_KEYWORDS or ep.has_auth or not tunnels(r):
            continue  # PAC can't carry a login; HTTP proxies without CONNECT can't load https:// pages
        entries.append(f"{PAC_KEYWORDS[r.ptype]} {ep.host}:{ep.port}")
        if len(entries) == PAC_MAX:
            break
    # no "; DIRECT" at the end: when every proxy is down the browser must not quietly use the real IP
    return PAC_TEMPLATE.format(when=f"{now:%Y-%m-%d %H:%M}", count=len(entries),
                               chain="; ".join(entries) or PAC_FAIL_CLOSED)


PROXIFIER_TYPES = {"http": "HTTPS", "socks4": "SOCKS4", "socks5": "SOCKS5"}  # "HTTPS" = HTTP proxy with CONNECT
PROXIFIER_MAX = 50  # a redundancy chain tries the entries in order; more only delays the failure case
PROXIFIER_OPTIONS = 48  # what Proxifier writes for a plain proxy entry (no UDP, no DNS through it)
PROXIFIER_CHAIN_ID = 200


def proxifier(rows: Sequence[CheckResult], now: datetime) -> str:
    """A Proxifier profile (.ppx, XML). All proxies go into one redundancy chain, which Proxifier walks in
    order until one answers – so the best proxies come first, like everywhere else. HTTP proxies only when
    they can CONNECT (Proxifier tunnels everything), SOCKS4 only without a login (SOCKS4 has no password)."""
    from xml.sax.saxutils import escape

    entries = []
    for r in rows:
        ep = parse_endpoint(r.proxy)
        if r.ptype not in PROXIFIER_TYPES or not tunnels(r) or (r.ptype == "socks4" and ep.has_auth):
            continue
        pid = 100 + len(entries)
        lines = [
            f'    <Proxy id="{pid}" type="{PROXIFIER_TYPES[r.ptype]}">',
            f"      <Options>{PROXIFIER_OPTIONS}</Options>",
            f"      <Port>{ep.port}</Port>",
            f"      <Address>{escape(ep.host)}</Address>",
        ]
        if ep.has_auth:
            lines += [
                '      <Authentication enabled="true">',
                f"        <Username>{escape(ep.user or '')}</Username>",
                f"        <Password>{escape(ep.password or '')}</Password>",
                "      </Authentication>",
            ]
        entries.append("\n".join([*lines, "    </Proxy>"]))
        if len(entries) == PROXIFIER_MAX:
            break
    ids = [100 + i for i in range(len(entries))]
    chain = [f'    <Chain id="{PROXIFIER_CHAIN_ID}" type="redundancy">', "      <Name>proxy-scraper</Name>",
             *(f'      <Proxy enabled="true">{i}</Proxy>' for i in ids), "    </Chain>"]
    default = (f'      <Action type="Chain">{PROXIFIER_CHAIN_ID}</Action>' if ids
               else '      <Action type="Block" />')  # no proxies: block rather than quietly go direct
    return "\n".join([
        '<?xml version="1.0" encoding="UTF-8"?>',
        f"<!-- proxy-scraper, {now:%Y-%m-%d %H:%M}, {len(entries)} proxies (fastest first, HTTP only with CONNECT) -->",
        '<ProxifierProfile version="102" platform="Windows" product_id="0" product_minver="400">',
        "  <Options>",
        "    <Resolve>",
        '      <AutoModeDetection enabled="true" />',
        '      <ViaProxy enabled="false">',
        '        <TryLocalDnsFirst enabled="false" />',
        "      </ViaProxy>",
        '      <ExclusionList OnlyFromListMode="false">%ComputerName%; localhost; *.local</ExclusionList>',
        "      <DnsUdpMode>0</DnsUdpMode>",
        "    </Resolve>",
        '    <Encryption mode="disabled" />',  # passwords are plain text below – "basic" would expect them encrypted
        '    <HttpProxiesSupport enabled="false" />',
        '    <HandleDirectConnections enabled="false" />',
        '    <ConnectionLoopDetection enabled="true" />',
        '    <ProcessServices enabled="false" />',
        '    <ProcessOtherUsers enabled="false" />',
        "  </Options>",
        "  <ProxyList>",
        *entries,
        "  </ProxyList>",
        "  <ChainList>",
        *(chain if ids else []),
        "  </ChainList>",
        "  <RuleList>",
        '    <Rule enabled="true">',
        "      <Name>Localhost</Name>",
        "      <Targets>localhost; 127.0.0.1; ::1; %ComputerName%</Targets>",
        '      <Action type="Direct" />',
        "    </Rule>",
        '    <Rule enabled="true">',
        "      <Name>Default</Name>",
        default,
        "    </Rule>",
        "  </RuleList>",
        "</ProxifierProfile>",
    ]) + "\n"


EXPORTERS: Dict[str, Tuple[str, Exporter]] = {
    "proxychains": ("proxychains.conf", proxychains),
    "clash": ("clash.yaml", clash),
    "singbox": ("singbox.json", singbox),
    "curl": ("curl.txt", curl),
    "pac": ("proxy.pac", pac),
    "proxifier": ("proxifier.ppx", proxifier),
}


def parse_exports(value: str) -> List[str]:
    """"clash,curl" -> ["clash", "curl"]; "all" -> all of them. Unknown names -> ValueError."""
    names = [n.strip().lower() for n in value.split(",") if n.strip()]
    unknown = [n for n in names if n not in EXPORTERS and n != "all"]
    if unknown:  # check before "all" – otherwise a typo in "all,clsh" would go unnoticed
        raise ValueError(f"unknown format: {', '.join(unknown)} (possible: {', '.join(EXPORTERS)}, all)")
    if "all" in names:
        return list(EXPORTERS)
    return [n for n in EXPORTERS if n in names]  # fixed order, no duplicates
