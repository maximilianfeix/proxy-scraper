"""The MCP server (#129): tools, schemas, annotations, errors, and a real stdio session.

Needs the MCP SDK (Python 3.10+): `pip install "proxy-scraper[mcp]"`. Without it only the entry point is tested.
"""

import asyncio
import subprocess
import sys

import pytest

from proxyscraper import agent, mcp_entry

from .test_agent import ROWS, STATS

needs_sdk = pytest.mark.skipif(sys.version_info < (3, 10), reason="the MCP SDK needs Python 3.10+")


def test_without_the_sdk_the_command_says_how_to_install_it(monkeypatch, capsys):
    monkeypatch.setattr(mcp_entry, "_load_server", lambda: (_ for _ in ()).throw(ImportError("x", name="mcp")))
    assert mcp_entry.main() == 1
    err = capsys.readouterr()
    assert 'pip install "proxy-scraper[mcp]"' in err.err and err.out == ""  # stdout belongs to the protocol


def test_old_python_is_told_what_it_needs(monkeypatch, capsys):
    monkeypatch.setattr(mcp_entry.sys, "version_info", (3, 9, 18))
    assert mcp_entry.main() == 1
    assert "3.10" in capsys.readouterr().err


# --------------------------------------------------------------------------- with the SDK

class FakeLive:
    async def get(self):
        return agent.LiveList(rows=ROWS, stats=STATS, loaded_at=0.0)


class FakeFetcher:
    def __init__(self):
        self.calls = []

    async def fetch(self, url, protocol="any", country="", max_chars=20000, raw_html=False):
        self.calls.append((url, protocol, country, max_chars, raw_html))
        agent.check_target(url)
        return {"url": url, "final_url": url, "status": 200, "content_type": "text/html", "via": "http://1.1.1.1:80",
                "proxy_country": "DE", "elapsed_ms": 42, "bytes": 5, "text": "hello", "truncated": False,
                "note": None}

    async def close(self):
        pass


def session(client_fn, fetcher=None):
    mcp = pytest.importorskip("mcp")  # noqa: F841
    from mcp.client.client import Client

    from proxyscraper import mcp_server

    server = mcp_server.build_server(live=FakeLive(), fetcher=fetcher or FakeFetcher())

    async def go():
        async with Client(server) as client:
            return await client_fn(client)
    return asyncio.run(go())


@needs_sdk
def test_three_tools_with_honest_annotations_and_schemas():
    async def go(client):
        return (await client.list_tools()).tools, client.instructions

    tools, instructions = session(go)
    by_name = {t.name: t for t in tools}
    assert set(by_name) == {"get_proxies", "check_proxies", "fetch_url"}
    get, check, fetch = by_name["get_proxies"], by_name["check_proxies"], by_name["fetch_url"]
    assert get.annotations.read_only_hint and get.annotations.idempotent_hint and get.annotations.open_world_hint
    assert fetch.annotations.read_only_hint and fetch.annotations.open_world_hint
    assert check.annotations.read_only_hint is False and check.annotations.destructive_hint is False
    for tool in tools:
        assert tool.title and len(tool.description) > 80 and tool.output_schema
        for name, prop in tool.input_schema["properties"].items():
            assert prop.get("description"), f"{tool.name}.{name} has no description"
    assert "password" in instructions.lower()


@needs_sdk
def test_get_proxies_returns_structured_proxies():
    async def go(client):
        return await client.call_tool("get_proxies", {"protocol": "http", "limit": 2})

    result = session(go)
    assert not result.is_error
    data = result.structured_content
    assert [p["url"] for p in data["proxies"]] == ["http://1.1.1.3:80", "http://1.1.1.5:80"]
    assert data["matched"] == 3 and data["list_updated"] == STATS["updated"] and data["note"] is None


@needs_sdk
def test_get_proxies_explains_a_shortage():
    async def go(client):
        return await client.call_tool("get_proxies", {"countries": ["US"], "limit": 5})

    data = session(go).structured_content
    assert data["matched"] == 1 and "DE (4)" in data["note"]


@needs_sdk
def test_bad_input_comes_back_as_a_tool_error_the_agent_can_fix():
    async def go(client):
        return await client.call_tool("get_proxies", {"countries": ["Germany"]})

    result = session(go)
    assert result.is_error and "two-letter" in result.content[0].text


@needs_sdk
def test_limit_is_bounded():
    async def go(client):
        return await client.call_tool("get_proxies", {"limit": 5000})

    assert session(go).is_error


@needs_sdk
def test_check_proxies_runs_the_fresh_check(monkeypatch):
    from proxyscraper.checker import CheckResult

    async def fake_find(**kwargs):
        return [CheckResult("socks5 3.3.3.3:1080", "socks5", "3.3.3.3:1080", 90, "9.9.9.9", https=True,
                            country="NL")]

    monkeypatch.setattr(agent, "find_proxies_async", fake_find)

    async def go(client):
        return await client.call_tool("check_proxies", {"want": 3, "protocol": "socks5"})

    data = session(go).structured_content
    assert [p["url"] for p in data["proxies"]] == ["socks5://3.3.3.3:1080"]
    assert data["mode"] == "live" and data["took_seconds"] >= 0


@needs_sdk
def test_fetch_url_returns_the_page_and_the_proxy():
    fetcher = FakeFetcher()

    async def go(client):
        return await client.call_tool("fetch_url", {"url": "https://example.com/", "country": "de",
                                                     "max_chars": 500})

    data = session(go, fetcher).structured_content
    assert data["status"] == 200 and data["text"] == "hello" and data["via"] == "http://1.1.1.1:80"
    assert fetcher.calls == [("https://example.com/", "any", "de", 500, False)]


@needs_sdk
def test_fetch_url_refuses_local_targets():
    async def go(client):
        return await client.call_tool("fetch_url", {"url": "http://192.168.1.1/admin"})

    result = session(go)
    assert result.is_error and "private" in result.content[0].text


@needs_sdk
def test_a_real_stdio_session_only_speaks_mcp_on_stdout():
    """Starts the server the way Claude Code or Cursor would. Anything else on stdout would break the protocol."""
    pytest.importorskip("mcp")
    from mcp.client.client import Client
    from mcp.client.stdio import StdioServerParameters

    params = StdioServerParameters(command=sys.executable, args=["-m", "proxyscraper.mcp_entry"])

    async def go():
        async with Client(params) as client:
            return sorted(t.name for t in (await client.list_tools()).tools), client.server_info

    names, info = asyncio.run(go())
    assert names == ["check_proxies", "fetch_url", "get_proxies"] and info.name == "proxy-scraper"


def test_the_entry_point_is_installed_with_the_package():
    out = subprocess.run([sys.executable, "-c", "from importlib.metadata import entry_points; "
                          "print([e.value for e in entry_points(group='console_scripts') "
                          "if e.name == 'proxy-scraper-mcp'])"], capture_output=True, text=True)
    assert "proxyscraper.mcp_entry:main" in out.stdout or "[]" in out.stdout  # [] = running from a checkout
