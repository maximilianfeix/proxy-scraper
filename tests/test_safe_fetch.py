"""Sources found automatically (other scrapers' configs) may only make us talk to public addresses.

Someone else's file must not point the scraper at localhost, the local network or a cloud metadata service –
not by an IP literal in any spelling, not by a name that resolves there (127.0.0.1.nip.io), not by a redirect,
and not by a second DNS answer between the check and the connect. All DNS here is faked; the only server is a
local one, reachable only through an explicit test policy that allows 127.0.0.1.
"""

import asyncio
import ipaddress
import json
import socket
import ssl

import pytest

from proxyscraper import netio
from proxyscraper import sources as srcs
from proxyscraper.netpolicy import PUBLIC_ONLY, BlockedTarget, TargetPolicy, is_public_address, parse_ip_literal

from .lab import DATA, client_context

LOCAL_ONLY = TargetPolicy(ports=None, allow_networks=(ipaddress.ip_network("127.0.0.1/32"),))
LIST = "\n".join(f"8.8.{i // 250}.{i % 250 + 1}:8080" for i in range(30)).encode()


# --------------------------------------------------------------------------- #
# addresses
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("ip", [
    "127.0.0.1", "10.1.2.3", "172.16.0.1", "192.168.1.1", "169.254.169.254", "100.64.0.1", "0.0.0.0",
    "224.0.0.1", "239.255.255.250", "240.0.0.1", "255.255.255.255", "192.0.2.1", "198.18.0.1",
    "::1", "::", "fe80::1", "fd00::1", "ff02::1", "ff0e::1", "2001:db8::1",
    "::ffff:127.0.0.1", "::ffff:10.0.0.1", "::127.0.0.1",          # IPv4-mapped / -compatible
    "64:ff9b::7f00:1", "64:ff9b::a00:1", "64:ff9b:1::1",            # NAT64 to loopback / private
    "2002:7f00:1::1", "2002:a00:1::1",                              # 6to4 around a private IPv4
    "2001:0:4136:e378:8000:63bf:80ff:fffe",                         # Teredo, client 127.0.0.1
])
def test_non_public_addresses(ip):
    assert not is_public_address(ipaddress.ip_address(ip))


@pytest.mark.parametrize("ip", ["8.8.8.8", "1.1.1.1", "2606:4700:4700::1111", "2001:4860:4860::8888",
                                "::ffff:8.8.8.8", "64:ff9b::808:808"])
def test_public_addresses(ip):
    assert is_public_address(ipaddress.ip_address(ip))


@pytest.mark.parametrize("host, ip", [
    ("127.0.0.1", "127.0.0.1"), ("127.1", "127.0.0.1"), ("0x7f.1", "127.0.0.1"), ("0x7f000001", "127.0.0.1"),
    ("2130706433", "127.0.0.1"), ("0177.0.0.1", "127.0.0.1"), ("017700000001", "127.0.0.1"),
    ("10.1", "10.0.0.1"), ("127.0.0.1.", "127.0.0.1"), ("::ffff:7f00:1", "::ffff:127.0.0.1"),
    ("[::1]", "::1"), ("134744072", "8.8.8.8"),
])
def test_alternative_ip_spellings_are_recognized(host, ip):
    assert parse_ip_literal(host) == ipaddress.ip_address(ip)


@pytest.mark.parametrize("host", ["example.org", "1e100.net", "123.example.com", "0x7g.1", "my-host"])
def test_names_are_not_ip_literals(host):
    assert parse_ip_literal(host) is None


@pytest.mark.parametrize("host", ["08.0.0.1", "1.2.3.4.5", "256.1.1.1", "4294967296", "1.2.70000", "fe80::1%eth0",
                                  "9" * 5000 + ".1", "0x" + "f" * 5000, "0" + "7" * 5000])
def test_numeric_hosts_that_are_no_valid_address_are_rejected(host):
    with pytest.raises(BlockedTarget):
        parse_ip_literal(host)


@pytest.mark.parametrize("url", [
    "https://127.1/proxy.txt", "https://0x7f.1/proxies.txt", "https://2130706433/proxy.txt",
    "https://0177.0.0.1/proxy.txt", "https://224.0.0.1/proxy.txt", "https://[ff0e::1]/proxy.txt",
    "https://[64:ff9b::7f00:1]/proxy.txt", "https://[::127.0.0.1]/proxy.txt",
])
def test_mined_urls_reject_every_spelling_of_a_private_address(url):
    assert srcs.mined_urls(url.encode()) == []


# --------------------------------------------------------------------------- #
# the policy against URLs, with fake DNS
# --------------------------------------------------------------------------- #

def fake_dns(table, calls=None):
    """getaddrinfo replacement: name -> list of addresses (or a function of the call number)."""
    async def getaddrinfo(host, port, *, family=0, type=0, proto=0, flags=0):
        if calls is not None:
            calls.append(host)
        answer = table.get(host)
        if callable(answer):
            answer = answer(sum(1 for h in calls or () if h == host))
        if answer is None:
            raise socket.gaierror(socket.EAI_NONAME, "unknown")
        return [(socket.AF_INET6 if ":" in a else socket.AF_INET, socket.SOCK_STREAM, 6, "",
                 (a, port or 0)) for a in answer]
    return getaddrinfo


def run_with_dns(table, coro_fn, calls=None):
    async def go():
        asyncio.get_running_loop().getaddrinfo = fake_dns(table, calls)
        return await coro_fn()
    return asyncio.run(go())


@pytest.mark.parametrize("url, table", [
    ("https://127.0.0.1.nip.io/proxies.txt", {"127.0.0.1.nip.io": ["127.0.0.1"]}),
    ("https://metadata.example/proxy.txt", {"metadata.example": ["169.254.169.254"]}),
    ("https://mixed.example/proxy.txt", {"mixed.example": ["8.8.8.8", "10.0.0.1"]}),  # one bad answer is enough
    ("https://v6.example/proxy.txt", {"v6.example": ["::ffff:127.0.0.1"]}),
    ("https://v6.example/proxy.txt", {"v6.example": ["fe80::1%en0"]}),
    ("https://nothing.example/proxy.txt", {"nothing.example": []}),
    ("https://example.org:8443/proxy.txt", {"example.org": ["8.8.8.8"]}),   # port
    ("ftp://example.org/proxy.txt", {"example.org": ["8.8.8.8"]}),          # scheme
    ("file:///etc/passwd", {}),
    ("https://user:pw@0x7f.1/proxy.txt", {}),
])
def test_public_only_policy_blocks_before_any_connection(url, table):
    with pytest.raises(BlockedTarget):
        run_with_dns(table, lambda: PUBLIC_ONLY.resolve(url))


def test_public_only_policy_returns_the_checked_addresses():
    target = run_with_dns({"lists.example": ["8.8.8.8", "2606:4700:4700::1111"]},
                          lambda: PUBLIC_ONLY.resolve("https://lists.example/proxy.txt"))
    assert (target.host, target.port, target.https) == ("lists.example", 443, True)
    assert target.addresses == ["8.8.8.8", "2606:4700:4700::1111"]


def test_blocked_targets_are_connection_errors():
    # callers (source downloads, discovery) already treat ConnectionError as "source unreachable"
    assert issubclass(BlockedTarget, ConnectionError)


# --------------------------------------------------------------------------- #
# http_request with a policy: a local server, reachable only via LOCAL_ONLY
# --------------------------------------------------------------------------- #

class Server:
    """Records each request (raw head) and answers with `reply(head)`."""

    def __init__(self, reply, context=None):
        self.reply, self.context, self.requests, self.sni = reply, context, [], []

    async def __aenter__(self):
        if self.context is not None:
            self.context.sni_callback = lambda sock, name, ctx: self.sni.append(name)
        self.server = await asyncio.start_server(self._handle, "127.0.0.1", 0, ssl=self.context)
        self.port = self.server.sockets[0].getsockname()[1]
        return self

    async def __aexit__(self, *exc):
        self.server.close()
        await self.server.wait_closed()

    async def _handle(self, reader, writer):
        try:
            head = await reader.readuntil(b"\r\n\r\n")
            self.requests.append(head)
            writer.write(self.reply(head))
            await writer.drain()
        except (ConnectionError, asyncio.IncompleteReadError, ssl.SSLError):
            pass
        finally:
            writer.close()


def ok(body=b"hello"):
    return lambda head: b"HTTP/1.1 200 OK\r\nContent-Length: %d\r\n\r\n" % len(body) + body


def redirect(location):
    return lambda head: b"HTTP/1.1 302 Found\r\nLocation: " + location.encode() + b"\r\nContent-Length: 0\r\n\r\n"


def test_a_name_resolving_to_loopback_is_never_contacted():
    async def go():
        async with Server(ok()) as srv:
            with pytest.raises(BlockedTarget):
                await netio.http_get(f"http://127.0.0.1.nip.io:{srv.port}/proxies.txt",
                                     policy=TargetPolicy(ports=None))  # public only, any port
            return srv.requests
    assert run_with_dns({"127.0.0.1.nip.io": ["127.0.0.1"]}, go) == []


def test_the_connection_goes_to_the_checked_address_not_to_a_second_dns_answer():
    calls = []

    async def go():
        async with Server(ok(b"list")) as srv:
            # first answer: the allowed address; any later lookup would get a different one (DNS rebinding)
            table = {"lists.test": lambda n: ["127.0.0.1"] if n == 1 else ["10.9.9.9"]}
            asyncio.get_running_loop().getaddrinfo = fake_dns(table, calls)
            body = await netio.http_get(f"http://lists.test:{srv.port}/proxy.txt", policy=LOCAL_ONLY)
            return body, srv.requests
    body, requests = asyncio.run(go())
    assert body == b"list"
    assert calls.count("lists.test") == 1  # resolved once, by the check
    assert b"\r\nHost: lists.test:" in requests[0]  # the Host header keeps the name


def test_tls_keeps_sni_and_certificate_check_on_the_hostname(monkeypatch):
    monkeypatch.setattr(netio, "ssl_context", client_context)  # trusts the lab certificate (localhost, 127.0.0.1)
    server_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_ctx.load_cert_chain(DATA / "localhost-cert.pem", DATA / "localhost-key.pem")

    async def go():
        async with Server(ok(b"secure"), server_ctx) as srv:
            body = await netio.http_get(f"https://localhost:{srv.port}/proxy.txt", policy=LOCAL_ONLY)
            # same IP, a name the certificate doesn't cover: verification is against the name, not the IP
            with pytest.raises(ssl.SSLCertVerificationError):
                await netio.http_request(f"https://lists.test:{srv.port}/proxy.txt", policy=LOCAL_ONLY,
                                         insecure_fallback=False)
            return body, srv.sni
    body, sni = run_with_dns({"localhost": ["127.0.0.1"], "lists.test": ["127.0.0.1"]}, go)
    assert body == b"secure" and sni[0] == "localhost"


@pytest.mark.parametrize("location, table", [
    ("http://internal.test:{port}/x", {"internal.test": ["10.0.0.1"]}),
    ("http://0x0a.1:{port}/x", {}),
    ("http://[::ffff:10.0.0.1]:{port}/x", {}),
    ("ftp://lists.test/x", {}),
    ("file:///etc/passwd", {}),
])
def test_every_redirect_hop_is_checked(location, table):
    async def go():
        async with Server(ok(b"secret")) as inner, Server(redirect(location.format(port=inner.port))) as outer:
            with pytest.raises(BlockedTarget):
                await netio.http_get(f"http://lists.test:{outer.port}/proxy.txt", policy=LOCAL_ONLY)
            return outer.requests, inner.requests
    outer, inner = run_with_dns({"lists.test": ["127.0.0.1"], **table}, go)
    assert len(outer) == 1 and inner == []


def test_public_only_default_ports_block_a_redirect_to_another_port():
    policy = TargetPolicy(allow_networks=(ipaddress.ip_network("127.0.0.1/32"),))  # ports 80/443 only

    async def go():
        with pytest.raises(BlockedTarget):
            await netio.http_get("http://lists.test:8080/proxy.txt", policy=policy)
    run_with_dns({"lists.test": ["127.0.0.1"]}, go)


def test_without_a_policy_requests_stay_unrestricted():
    # explicitly configured sources (sources.json, --source http://127.0.0.1:…) keep working
    async def go():
        async with Server(ok(b"own")) as srv:
            return await netio.http_get(f"http://127.0.0.1:{srv.port}/list.txt")
    assert asyncio.run(go()) == b"own"


# --------------------------------------------------------------------------- #
# discovery uses the policy for mined URLs
# --------------------------------------------------------------------------- #

def test_mined_urls_are_fetched_public_only_by_default():
    fetched = []
    config = json.dumps(["https://127.0.0.1.nip.io/proxies.txt"]).encode()

    async def get(url, timeout=0, headers=None):  # the trusted getter (GitHub API, raw configs)
        fetched.append(url)
        return config if url == "cfg" else LIST

    async def go():
        async with Server(ok(LIST)) as srv:
            found = await srcs._mine(get, ["cfg"], set())
            return found, srv.requests
    found, requests = run_with_dns({"127.0.0.1.nip.io": ["127.0.0.1"]}, go)
    assert found == {} and fetched == ["cfg"] and requests == []


def test_netio_public_get_is_http_get_with_the_public_only_policy(monkeypatch):
    seen = {}

    async def fake_request(url, timeout=15.0, headers=None, max_redirects=3, policy=None, **kw):
        seen.update(url=url, policy=policy)
        return 200, {}, b"x"

    monkeypatch.setattr(netio, "http_request", fake_request)
    assert asyncio.run(netio.public_get("https://lists.example/p.txt")) == b"x"
    assert seen["policy"] is PUBLIC_ONLY
