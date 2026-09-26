"""MCP server: working free proxies for AI agents, and pages fetched through them.

Three tools – the logic lives in agent.py, this module describes it for agents (names, parameter docs,
structured results, annotations) and turns AgentError into tool errors the agent can act on.
Start it with `proxy-scraper-mcp` (stdio); needs `pip install "proxy-scraper[mcp]"` and Python 3.10+.
"""

import contextlib
import logging
import sys
import time
from typing import Annotated, List, Literal, Optional

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from . import __version__, agent

REPO = "https://github.com/maximilianfeix/proxy-scraper"

INSTRUCTIONS = """\
Free HTTP, SOCKS4 and SOCKS5 proxies that passed real checks: a protocol handshake, the same exit IP on two \
unrelated sites (drops honeypots), a byte-for-byte content check (drops proxies that inject scripts) and, for \
HTTPS, a verified TLS handshake.

- get_proxies: instant, from a list re-checked every hour. Start here.
- check_proxies: checks from this machine's network, so the results work from here right now. Takes 30-90 s.
- fetch_url: loads a page through a verified proxy and switches proxies by itself if one fails.

Free proxies are run by strangers: never send passwords, cookies, API keys or personal data through them, \
and expect some of them to stop working at any time."""

Protocol = Literal["any", "http", "socks4", "socks5"]
Countries = Annotated[List[str], Field(description="Two-letter country codes of the exit IP, e.g. ['DE', 'NL']. "
                                                   "Empty = any country.")]


class Proxy(BaseModel):
    url: str = Field(description="Ready to use, e.g. socks5://1.2.3.4:1080 – curl, requests, httpx and "
                                 "browsers take it as it is")
    protocol: str = Field(description="http, socks4 or socks5")
    address: str = Field(description="ip:port")
    country: Optional[str] = Field(description="Two-letter code of the exit IP's country")
    latency_ms: Optional[int] = Field(description="Response time in the last check")
    https: Optional[bool] = Field(description="Tunnels HTTPS with a verified TLS handshake")
    anonymity: Optional[str] = Field(description="elite (target sees no proxy), anonymous or transparent")
    provider: Optional[str] = Field(description="Network the exit IP belongs to")
    datacenter: Optional[bool] = Field(description="Exit IP in a datacenter – some sites block those")
    blocklisted: Optional[bool] = Field(description="Exit IP on the SpamCop blocklist – expect captchas")
    up_for_hours: Optional[int] = Field(description="How long it has worked without a gap (live list only)")


class ProxyList(BaseModel):
    proxies: List[Proxy] = Field(description="Fastest first")
    matched: int = Field(description="How many proxies in the list pass the filters (limit cuts the rest)")
    list_updated: Optional[str] = Field(description="When the list was last checked (ISO 8601, UTC)")
    list_age_minutes: Optional[int] = Field(description="Minutes since that check")
    note: Optional[str] = Field(description="What to do if fewer proxies matched than asked for")


class FreshProxies(BaseModel):
    proxies: List[Proxy] = Field(description="Working from this machine right now, fastest first")
    mode: str = Field(description="live = the hourly list checked again, full = all 700+ sources")
    took_seconds: float
    note: Optional[str] = Field(description="What to do if none were found")


class Page(BaseModel):
    url: str
    final_url: Optional[str] = Field(description="After redirects")
    status: int = Field(description="HTTP status of the target, e.g. 200, 403, 404")
    content_type: Optional[str]
    via: Optional[str] = Field(description="The proxy that delivered the page")
    proxy_country: Optional[str] = Field(description="Country the target saw the request from")
    elapsed_ms: int
    bytes: int = Field(description="Size of the response body")
    text: str = Field(description="Readable text (HTML is turned into plain text unless raw_html is set)")
    truncated: bool = Field(description="True if the text was cut at max_chars")
    note: Optional[str]


def _fail(e: agent.AgentError):
    raise ToolError(str(e)) from None


def build_server(live: Optional[agent.LiveSource] = None, fetcher: Optional[agent.PageFetcher] = None) -> MCPServer:
    live = live or agent.LiveSource()
    fetcher = fetcher or agent.PageFetcher(live)

    @contextlib.asynccontextmanager
    async def lifespan(_server):
        try:
            yield {}
        finally:
            await fetcher.close()  # the internal rotating server

    server = MCPServer("proxy-scraper", title="proxy-scraper – free proxies that actually work",
                       version=__version__, instructions=INSTRUCTIONS, website_url=REPO, lifespan=lifespan)

    @server.tool(title="Get working proxies",
                 annotations=ToolAnnotations(read_only_hint=True, idempotent_hint=True, open_world_hint=True))
    async def get_proxies(
        protocol: Annotated[Protocol, Field(description="Proxy protocol. socks5 works for any TCP traffic, http is "
                                                        "what most HTTP clients expect.")] = "any",
        countries: Countries = [],  # noqa: B006 – pydantic copies defaults, and a list reads best in the schema
        https_only: Annotated[bool, Field(description="Only proxies that tunnel HTTPS with verified TLS. "
                                                      "Needed for https:// sites.")] = False,
        elite_only: Annotated[bool, Field(description="Only proxies the target can't recognize as proxies")] = False,
        exclude_datacenter: Annotated[bool, Field(description="Skip exits in datacenters (blocked by many "
                                                              "sites)")] = False,
        exclude_blocklisted: Annotated[bool, Field(description="Skip exits on the SpamCop blocklist (fewer "
                                                               "captchas)")] = False,
        stable_only: Annotated[bool, Field(description="Only proxies that have worked for 24 h or more")] = False,
        max_latency_ms: Annotated[int, Field(ge=0, description="Maximum response time, 0 = any")] = 0,
        limit: Annotated[int, Field(ge=1, le=100, description="How many to return (fastest first)")] = 10,
    ) -> ProxyList:
        """Get working free proxies right now, fastest first.

        Instant: comes from a public list that is re-checked every hour from GitHub's servers, so a proxy may have
        died since, and some behave differently from this machine's network. Use check_proxies when they must
        work from here right now. Every result has a ready-to-use url like socks5://1.2.3.4:1080."""
        try:
            data = await live.get()
            rows = agent.select(data.rows, protocol, countries, https_only, elite_only, exclude_datacenter,
                                exclude_blocklisted, stable_only, max_latency_ms, data.run_hours)
        except agent.AgentError as e:
            _fail(e)
        return ProxyList(proxies=[Proxy(**agent.describe(r, data.run_hours)) for r in rows[:limit]],
                         matched=len(rows), list_updated=data.updated or None, list_age_minutes=data.age_minutes(),
                         note=agent.shortage_note(data.rows, limit, len(rows), countries))

    @server.tool(title="Check proxies from this machine",
                 annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False,
                                             open_world_hint=True))
    async def check_proxies(
        ctx: Context,
        want: Annotated[int, Field(ge=1, le=100, description="Stop once this many work")] = 10,
        protocol: Annotated[Protocol, Field(description="Proxy protocol to look for")] = "any",
        countries: Countries = [],  # noqa: B006
        https_only: Annotated[bool, Field(description="Only proxies that tunnel HTTPS with verified TLS")] = False,
        elite_only: Annotated[bool, Field(description="Only proxies the target can't recognize as proxies")] = False,
        exclude_datacenter: Annotated[bool, Field(description="Skip exits in datacenters")] = False,
        exclude_blocklisted: Annotated[bool, Field(description="Skip exits on the SpamCop blocklist")] = False,
        max_latency_ms: Annotated[int, Field(ge=0, description="Maximum response time, 0 = any")] = 0,
        mode: Annotated[Literal["live", "full"], Field(description="live: check the hourly list again from here "
                                                                   "(30-90 s). full: collect from all 700+ "
                                                                   "sources (a few minutes)")] = "live",
    ) -> FreshProxies:
        """Find proxies that work from this machine's network right now.

        Runs the same checks as the public list – handshake, honeypot test, byte-for-byte content check, verified
        TLS – but from here, so the results were verified seconds ago from the network your code runs on. Slower
        than get_proxies: 30-90 s in live mode, and progress is reported while it runs. It also updates the local
        statistics proxy-scraper learns from."""
        started = time.monotonic()

        async def progress(elapsed: float, message: str):
            await ctx.report_progress(elapsed, None, message)

        try:
            found = await agent.check_fresh(want, protocol, countries, https_only, elite_only, exclude_datacenter,
                                            exclude_blocklisted, max_latency_ms, mode, progress)
        except agent.AgentError as e:
            _fail(e)
        note = None if found else ("Nothing passed from this machine. A firewall may block proxy ports – "
                                   "try get_proxies, or mode='full'.")
        return FreshProxies(proxies=[Proxy(**p) for p in found], mode=mode,
                            took_seconds=round(time.monotonic() - started, 1), note=note)

    @server.tool(title="Fetch a page through a proxy",
                 annotations=ToolAnnotations(read_only_hint=True, idempotent_hint=False, open_world_hint=True))
    async def fetch_url(
        url: Annotated[str, Field(description="Full http:// or https:// URL of a public site")],
        country: Annotated[str, Field(description="Two-letter code: load the page as seen from this country. "
                                                  "Empty = any country.")] = "",
        protocol: Annotated[Protocol, Field(description="Only use proxies of this protocol")] = "any",
        max_chars: Annotated[int, Field(ge=100, le=200_000, description="Cut the text after this many "
                                                                        "characters")] = 20_000,
        raw_html: Annotated[bool, Field(description="Return the HTML as it is instead of readable "
                                                    "text")] = False,
    ) -> Page:
        """Load a web page through a verified free proxy and return it as readable text.

        If a proxy fails, the next one is tried by itself. HTTPS only goes through proxies that passed a
        verified-TLS test, so the page can't be changed on the way. Useful to see a site from another country or
        when a site blocks this machine. GET only; don't use it for logins or anything with personal data."""
        try:
            page = await fetcher.fetch(url, protocol=protocol, country=country, max_chars=max_chars,
                                       raw_html=raw_html)
        except agent.AgentError as e:
            _fail(e)
        return Page(**page)

    return server


def serve() -> int:
    # stdout carries the protocol: the terminal UI and every log line go to stderr
    from rich.console import Console

    from .ui import widgets
    widgets.console = Console(stderr=True, highlight=False)
    logging.basicConfig(stream=sys.stderr, level=logging.WARNING)
    build_server().run("stdio")
    return 0


if __name__ == "__main__":
    sys.exit(serve())
