"""The live dashboard of the rotating server (/__proxy-scraper/) and the status fields it reads (#240)."""

import asyncio
import json
import re

from proxyscraper.server import RotatingServer, status
from proxyscraper.server.core import RequestLog

from .test_serve_api import _get, pool, result


def run(client, password="", recent=()):
    async def go():
        server = RotatingServer(pool(result(1), result(2, country="US"), result(3, country="US")), port=0,
                                timeout=3, password=password)
        server.stats.recent.extend(recent)
        await server.start()
        try:
            return await client(server.port, server)
        finally:
            await server.close()
    return asyncio.run(go())


def split(response):
    head, _, body = response.partition(b"\r\n\r\n")
    return head.decode(), body


def test_the_dashboard_is_a_self_contained_page():
    async def client(port, _):
        return await _get(port, "/__proxy-scraper/"), await _get(port, "/__proxy-scraper/dashboard")

    root, alias = run(client)
    head, body = split(root)
    assert head.startswith("HTTP/1.1 200") and "text/html" in head
    assert split(alias)[1] == body
    page = body.decode()
    assert "<title>proxy-scraper" in page and "/__proxy-scraper/status" in page
    # runs offline next to the server: nothing loaded from other hosts (a plain link to the docs is fine)
    assert not re.search(r"""src=["']https?://""", page)
    assert not re.search(r"""<link[^>]+href=["']https?://""", page)
    assert "@import" not in page


def test_the_dashboard_sends_a_strict_content_security_policy():
    async def client(port, _):
        return await _get(port, "/__proxy-scraper/")

    head, _ = split(run(client))
    csp = re.search(r"Content-Security-Policy: ([^\r\n]+)", head).group(1)
    assert "default-src 'none'" in csp and "connect-src 'self'" in csp and "frame-ancestors 'none'" in csp
    assert "X-Content-Type-Options: nosniff" in head


def test_client_data_is_only_ever_rendered_as_text():
    """Target hosts come from whoever uses the proxy – they must never reach innerHTML."""
    async def client(port, _):
        return await _get(port, "/__proxy-scraper/")

    page = split(run(client))[1].decode()
    assert "innerHTML" not in page and "insertAdjacentHTML" not in page and "document.write" not in page
    assert "textContent" in page


def test_the_dashboard_wants_the_server_password():
    async def client(port, _):
        return await _get(port, "/__proxy-scraper/"), await _get(port, "/__proxy-scraper/", auth=b"any:s3cret")

    denied, allowed = run(client, password="s3cret")
    assert denied.startswith(b"HTTP/1.1 401") and allowed.startswith(b"HTTP/1.1 200")


def test_status_lists_the_latest_connections_newest_first():
    recent = [RequestLog("127.0.0.1:5000", "example.com:443", "http 10.0.0.1:80", True, 120, 1),
              RequestLog("127.0.0.1:5001", "<b>evil</b>:80", "", False, 3000, 3)]

    async def client(port, _):
        return await _get(port, "/__proxy-scraper/status")

    data = json.loads(split(run(client, recent=recent))[1])
    assert data["recent"] == [
        {"target": "<b>evil</b>:80", "via": "", "ok": False, "ms": 3000, "attempts": 3},
        {"target": "example.com:443", "via": "http 10.0.0.1:80", "ok": True, "ms": 120, "attempts": 1},
    ]
    assert "client" not in data["recent"][0]  # who used the proxy isn't the dashboard's business


def test_status_counts_the_usable_proxies_per_country():
    async def client(port, server):
        server.pool.entries[0].disabled = True
        return await _get(port, "/__proxy-scraper/status")

    data = json.loads(split(run(client))[1])
    assert data["countries"] == {"US": 2}


def test_unknown_paths_still_404_and_point_to_the_dashboard():
    async def client(port, _):
        return await _get(port, "/__proxy-scraper/nope")

    head, body = split(run(client))
    assert head.startswith("HTTP/1.1 404") and b"/__proxy-scraper/" in body


def test_the_page_is_the_module_constant():
    assert status.DASHBOARD_HTML.startswith(b"<!doctype html>")


def test_the_tab_icon_is_inline_so_the_browser_never_asks_the_proxy_for_favicon_ico():
    page = status.DASHBOARD_HTML.decode()
    assert '<link rel="icon" href="data:image/svg+xml,' in page


def test_status_never_shows_an_upstream_password():
    recent = [RequestLog("127.0.0.1:5000", "example.com:443", "socks5://alice:secret@1.2.3.4:1080", True, 90, 1)]

    async def client(port, _):
        return await _get(port, "/__proxy-scraper/status")

    body = split(run(client, recent=recent))[1].decode()
    assert "secret" not in body
    assert json.loads(body)["recent"][0]["via"] == "socks5://alice:•••@1.2.3.4:1080"


def test_status_says_whether_the_proxy_wants_a_password():
    async def client(port, _):
        return await _get(port, "/__proxy-scraper/status", auth=b"any:s3cret")

    assert json.loads(split(run(client, password="s3cret"))[1])["auth"] is True
    assert json.loads(split(run(lambda port, _: _get(port, "/__proxy-scraper/status")))[1])["auth"] is False


def test_the_page_fetches_without_credentials_in_the_url():
    """Opened as http://user:pw@host/…, a relative fetch would inherit the login – and fetch refuses such URLs."""
    page = status.DASHBOARD_HTML.decode()
    assert 'new URL("/__proxy-scraper/status", location.origin)' in page


def test_the_copied_command_uses_the_address_in_the_browser_and_asks_for_the_password():
    page = status.DASHBOARD_HTML.decode()
    assert "location.host" in page  # not the bind address – 0.0.0.0 is no proxy address for a client
    assert "any:PASSWORD@" in page  # with --serve-password the command must carry the login


async def _get_host(port, path, host, auth=None):
    import base64
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    extra = f"Authorization: Basic {base64.b64encode(auth).decode()}\r\n" if auth else ""
    writer.write(f"GET {path} HTTP/1.1\r\nHost: {host}\r\n{extra}\r\n".encode())
    await writer.drain()
    data = await asyncio.wait_for(reader.read(1 << 20), 5)
    writer.close()
    return data


def test_without_a_password_only_ip_or_localhost_hosts_get_the_status():
    """DNS rebinding: a website points its own name at 127.0.0.1 and reads the status same-origin.
    Its name is in the Host header – an IP address or localhost is not."""
    async def client(port, _):
        return [await _get_host(port, path, host) for path, host in [
            ("/__proxy-scraper/status", "evil.example"),
            ("/__proxy-scraper/", f"evil.example:{port}"),
            ("/__proxy-scraper/metrics", "rebind.attacker.test"),
            ("/__proxy-scraper/status", f"127.0.0.1:{port}"),
            ("/__proxy-scraper/status", f"localhost:{port}"),
            ("/__proxy-scraper/status", f"[::1]:{port}"),
            ("/__proxy-scraper/status", "192.168.1.20"),
        ]]

    answers = [r.split(b"\r\n", 1)[0] for r in run(client)]
    assert answers[:3] == [b"HTTP/1.1 403 Forbidden"] * 3
    assert answers[3:] == [b"HTTP/1.1 200 OK"] * 4


def test_with_a_password_any_host_name_works():
    async def client(port, _):
        return await _get_host(port, "/__proxy-scraper/status", "proxy.example.com", auth=b"any:s3cret")

    assert run(client, password="s3cret").startswith(b"HTTP/1.1 200")


def test_the_csp_hash_survives_windows_line_endings():
    """Browsers hash an inline script after turning CRLF into LF – so must the server."""
    lf = status._dashboard_headers(b"<script>\nrun();\n</script>")
    crlf = status._dashboard_headers(b"<script>\r\nrun();\r\n</script>")
    assert lf == crlf


def test_the_chart_starts_over_after_the_tab_was_hidden():
    page = status.DASHBOARD_HTML.decode()
    handler = page.split('addEventListener("visibilitychange"', 1)[1].split("});", 1)[0]
    assert "history.length = 0" in handler and "last = null" in handler
