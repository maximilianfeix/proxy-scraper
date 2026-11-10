"""Proxy pool API (/get, /pop, /all, /count, /delete, /report) – proxy_pool compatible, on the --serve port."""

import asyncio
import base64
import json
import random

import pytest

from proxyscraper.checker import CheckResult
from proxyscraper.server import ProxyPool, RotatingServer, api


def result(n, latency=100, country="DE", ptype="http", https=True, anonymity="elite"):
    proxy = f"10.0.0.{n}:80"
    return CheckResult(f"{ptype} {proxy}", ptype, proxy, latency, "9.9.9.9", https=https, country=country,
                       anonymity=anonymity)


def pool(*results):
    return ProxyPool(list(results), rng=random.Random(1))


def call(p, target):
    status, kind, body = api.handle(p, target.encode())
    return status, kind, (json.loads(body) if kind == api.JSON_TYPE and body else body.decode())


def test_get_returns_proxy_pool_fields_and_ours():
    status, _, got = call(pool(result(1)), "/get")
    assert status == b"200 OK"
    assert got["proxy"] == "10.0.0.1:80" and got["url"] == "http://10.0.0.1:80"
    # what proxy_pool clients read
    assert got["https"] is True and got["region"] == "DE" and got["anonymous"] is True
    assert {"check_count", "fail_count", "last_status", "source"} <= got.keys()


def test_get_filters():
    p = pool(result(1, country="DE", ptype="http", https=False),
             result(2, country="US", ptype="socks5", latency=900),
             result(3, country="FR", ptype="socks4", anonymity="anonymous"))
    assert call(p, "/get?country=us")[2]["proxy"] == "10.0.0.2:80"
    assert call(p, "/get?protocol=socks4")[2]["proxy"] == "10.0.0.3:80"
    assert call(p, "/get?type=socks5")[2]["proxy"] == "10.0.0.2:80"
    assert call(p, "/get?anonymity=elite&max_latency=500")[2]["proxy"] == "10.0.0.1:80"
    assert {call(p, "/get?type=https")[2]["proxy"] for _ in range(20)} == {"10.0.0.2:80", "10.0.0.3:80"}
    assert call(p, "/get?country=DE,FR&https=1")[2]["proxy"] == "10.0.0.3:80"


def test_get_without_a_match_is_404_with_the_proxy_pool_body():
    status, _, got = call(pool(result(1, country="DE")), "/get?country=JP")
    assert status == b"404 Not Found" and got["src"] == "no proxy" and "proxy" not in got


def test_disabled_proxies_are_not_handed_out():
    p = pool(result(1), result(2))
    p.entries[0].disabled = True
    assert {call(p, "/get")[2]["proxy"] for _ in range(10)} == {p.entries[1].result.proxy}


def test_txt_format_for_shell_use():
    p = pool(result(1, latency=300), result(2, latency=100, ptype="socks5"))
    assert call(p, "/get?format=txt&type=socks5")[2] == "socks5://10.0.0.2:80\n"
    assert call(p, "/all?format=txt")[2] == "socks5://10.0.0.2:80\nhttp://10.0.0.1:80\n"  # best first
    assert call(p, "/get?format=txt&country=JP")[:2] == (b"404 Not Found", api.TEXT_TYPE)


def test_all_is_best_first_and_limited():
    p = pool(result(1, latency=500), result(2, latency=100), result(3, latency=300))
    assert [x["proxy"] for x in call(p, "/all")[2]] == ["10.0.0.2:80", "10.0.0.3:80", "10.0.0.1:80"]
    assert [x["proxy"] for x in call(p, "/all?limit=1")[2]] == ["10.0.0.2:80"]


def test_pop_takes_the_proxy_out():
    p = pool(result(1))
    assert call(p, "/pop")[2]["proxy"] == "10.0.0.1:80"
    assert p.entries == [] and call(p, "/get")[0] == b"404 Not Found"


def test_count():
    p = pool(result(1, country="DE"), result(2, country="DE", ptype="socks5", https=False), result(3, country="US"))
    got = call(p, "/count")[2]["count"]
    assert got["total"] == 3 and got["https"] == 2
    assert got["by_type"] == {"http": 2, "socks4": 0, "socks5": 1}
    assert list(got["by_country"].items()) == [("DE", 2), ("US", 1)]


def test_delete_by_address_or_url():
    p = pool(result(1), result(2, ptype="socks5"))
    assert call(p, "/delete?proxy=10.0.0.1:80")[2]["src"] == "success"
    assert call(p, "/delete?proxy=http://10.0.0.2:80")[0] == b"404 Not Found"  # it's a socks5 one
    assert call(p, "/delete?proxy=socks5://10.0.0.2:80")[0] == b"200 OK"
    assert p.entries == []


def test_report_counts_failures_until_the_proxy_drops_out():
    p = pool(result(1), result(2))
    for _ in range(3):
        got = call(p, "/report?proxy=10.0.0.1:80&ok=0")[2]
    assert got["disabled"] is True and len(p.usable) == 1
    assert call(p, "/report?proxy=10.0.0.2:80&ok=1")[2]["disabled"] is False


@pytest.mark.parametrize("target", ["/get?protocol=ftp", "/get?anonymity=superb", "/all?limit=x",
                                    "/delete", "/get?max_latency=fast"])
def test_bad_parameters_are_400(target):
    assert call(pool(result(1)), target)[0] == b"400 Bad Request"


def test_index_and_unknown_paths():
    assert "/get" in call(pool(), "/")[2]["endpoints"]
    status, _, got = call(pool(), "/nope")
    assert status == b"404 Not Found" and "src" not in got  # not "no proxy" – the path is wrong


async def _get(port, path, auth=None):
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    extra = f"Authorization: Basic {base64.b64encode(auth).decode()}\r\n" if auth else ""
    writer.write(f"GET {path} HTTP/1.1\r\nHost: 127.0.0.1\r\n{extra}\r\n".encode())
    await writer.drain()
    # the server closes after the response: read to the end, a big page can arrive in several chunks (#286)
    data = await asyncio.wait_for(reader.read(), 5)
    writer.close()
    return data


def run_server(client, password=""):
    async def go():
        server = RotatingServer(pool(result(1), result(2, country="US")), port=0, timeout=3, password=password)
        await server.start()
        try:
            return await client(server.port)
        finally:
            await server.close()
    return asyncio.run(go())


def test_api_answers_on_the_proxy_port():
    async def client(port):
        return await _get(port, "/get?country=US"), await _get(port, "/__proxy-scraper/status")

    got, status = run_server(client)
    head, _, body = got.partition(b"\r\n\r\n")
    assert head.startswith(b"HTTP/1.1 200") and b"application/json" in head
    assert json.loads(body)["proxy"] == "10.0.0.2:80"
    assert status.startswith(b"HTTP/1.1 200")  # the status page still wins over the API


def test_api_wants_the_server_password():
    async def client(port):
        return await _get(port, "/get"), await _get(port, "/get", auth=b"any:s3cret")

    denied, allowed = run_server(client, password="s3cret")
    assert denied.startswith(b"HTTP/1.1 401") and allowed.startswith(b"HTTP/1.1 200")


def test_the_helper_reads_a_response_that_arrives_in_parts():
    """A big page can reach the client in several chunks; one read() only gets the first (#286)."""
    async def go():
        async def serve(reader, writer):
            await reader.readuntil(b"\r\n\r\n")
            writer.write(b"HTTP/1.1 200 OK\r\nConnection: close\r\n\r\nfirst half, ")
            await writer.drain()
            await asyncio.sleep(0.05)
            writer.write(b"second half")
            await writer.drain()
            writer.close()

        server = await asyncio.start_server(serve, "127.0.0.1", 0)
        try:
            return await _get(server.sockets[0].getsockname()[1], "/")
        finally:
            server.close()
            await server.wait_closed()

    assert asyncio.run(go()).endswith(b"first half, second half")


async def _request(port, path, headers=()):
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    extra = "".join(f"{name}: {value}\r\n" for name, value in headers)
    writer.write(f"GET {path} HTTP/1.1\r\n{extra}\r\n".encode())
    await writer.drain()
    data = await asyncio.wait_for(reader.read(), 5)
    writer.close()
    return data


def test_without_a_password_a_host_name_gets_no_api_answer():
    """DNS rebinding: a website points its own name at 127.0.0.1 and reads /all same-origin – its name is in the
    Host header. Without a password the API only answers to an IP address or localhost."""
    async def client(port):
        return {host: await _request(port, "/all", [("Host", host)]) for host in
                ["evil.example", f"evil.example:{port}", f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}"]}

    answers = run_server(client)
    assert answers.pop("evil.example").startswith(b"HTTP/1.1 403")
    assert answers.pop(next(h for h in answers if h.startswith("evil"))).startswith(b"HTTP/1.1 403")
    assert all(a.startswith(b"HTTP/1.1 200") for a in answers.values())


def test_with_a_password_a_host_name_may_use_the_api():
    auth = "Basic " + base64.b64encode(b"any:s3cret").decode()

    async def client(port):
        return await _request(port, "/get", [("Host", "proxy.example.com"), ("Authorization", auth)])

    assert run_server(client, password="s3cret").startswith(b"HTTP/1.1 200")


@pytest.mark.parametrize("path", ["/delete?proxy=10.0.0.1:80", "/pop", "/report?proxy=10.0.0.1:80&ok=0",
                                  "/delete/?proxy=10.0.0.1:80"])
@pytest.mark.parametrize("headers", [
    [("Sec-Fetch-Site", "cross-site")],          # <img src="http://127.0.0.1:8899/delete?..."> elsewhere
    [("Sec-Fetch-Site", "same-site")],
    [("Origin", "https://evil.example")],        # older browsers: only Origin
    [("Origin", "null")],
])
def test_another_website_cannot_change_the_pool(path, headers):
    async def client(port):
        answer = await _request(port, path, [("Host", f"127.0.0.1:{port}"), *headers])
        return answer, await _request(port, "/count", [("Host", f"127.0.0.1:{port}")])

    answer, count = run_server(client)
    assert answer.startswith(b"HTTP/1.1 403")
    assert json.loads(count.partition(b"\r\n\r\n")[2])["count"]["total"] == 2  # nothing was taken out


def test_curl_and_the_servers_own_pages_can_still_change_the_pool():
    async def client(port):
        host = ("Host", f"127.0.0.1:{port}")
        return [await _request(port, "/report?proxy=10.0.0.1:80&ok=0", [host]),  # curl: no Origin, no Sec-Fetch
                await _request(port, "/report?proxy=10.0.0.1:80&ok=0", [host, ("Sec-Fetch-Site", "none")]),
                await _request(port, "/delete?proxy=10.0.0.1:80", [host, ("Sec-Fetch-Site", "same-origin"),
                                                                   ("Origin", f"http://127.0.0.1:{port}")]),
                await _request(port, "/get", [host, ("Sec-Fetch-Site", "cross-site")])]  # reading: CORS guards it

    assert all(a.startswith(b"HTTP/1.1 200") for a in run_server(client))


def _with_login():
    return pool(CheckResult("http alice:pa55@10.0.0.9:80", "http", "alice:pa55@10.0.0.9:80", 50, "9.9.9.9",
                            https=True, country="DE"))


def test_upstream_logins_are_masked_without_a_password():
    p = _with_login()
    got = call(p, "/get")[2]
    assert got["proxy"] == "alice:•••@10.0.0.9:80" and got["url"] == "http://alice:•••@10.0.0.9:80"
    assert "pa55" not in json.dumps(call(p, "/all")[2], ensure_ascii=False)
    assert "pa55" not in call(p, "/all?format=txt")[2] + call(p, "/get?format=txt")[2]
    deleted = call(p, "/delete?proxy=10.0.0.9:80")[2]  # found by its address, the login stays hidden
    assert deleted["src"] == "success" and "pa55" not in deleted["proxy"] and p.entries == []


def test_with_a_password_the_api_hands_out_the_full_login():
    got = api.handle(_with_login(), b"/get?format=txt", show_credentials=True)[2]
    assert got == b"http://alice:pa55@10.0.0.9:80\n"

    async def client(port):
        return await _get(port, "/get", auth=b"any:s3cret")

    async def go():
        server = RotatingServer(_with_login(), port=0, timeout=3, password="s3cret")
        await server.start()
        try:
            return await client(server.port)
        finally:
            await server.close()

    assert json.loads(asyncio.run(go()).partition(b"\r\n\r\n")[2])["url"] == "http://alice:pa55@10.0.0.9:80"
