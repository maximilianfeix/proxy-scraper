"""A proxy lab on localhost: check targets and proxies that each misbehave in one known way.

Everything a check needs is here and nothing leaves the machine: a target that returns the exit IP (plain and
behind TLS), a second target that answers like httpbin.org (/get, /html), and HTTP proxies that forward to them.
"Exit IPs" are documentation addresses (203.0.113.x, RFC 5737): the targets know which proxy a connection came
through and answer with that proxy's address.

Used by the tests of the check states and by docs/demo – a demo of the tool, not a measurement of real proxies.
"""

from __future__ import annotations

import asyncio
import json
import ssl
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set

from proxyscraper import checker as ck
from proxyscraper.checkstate import CONFIRM, CONTENT, HTTPS
from proxyscraper.judges import Judge

DATA = Path(__file__).parent / "data"
PAGE = (b"<!DOCTYPE html><html><head><title>Lab page</title></head><body><h1>Herman Melville - Moby-Dick</h1>"
        b"<p>Call me Ishmael.</p></body></html>")
INJECTED = PAGE.replace(b"</body>", b'<script src="http://203.0.113.99/ad.js"></script></body>')
OWN_IP = "203.0.113.1"  # what the targets see when this machine asks them directly


def _context(cert: str, key: str) -> ssl.SSLContext:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(DATA / cert, DATA / key)
    return ctx


def client_context() -> ssl.SSLContext:
    """Trusts the lab's certificate and nothing else – like certifi would trust a real one."""
    return ssl.create_default_context(cafile=str(DATA / "localhost-cert.pem"))


async def _pipe(reader, writer) -> None:
    try:
        while True:
            data = await reader.read(65536)
            if not data:
                break
            writer.write(data)
            await writer.drain()
    except (ConnectionError, OSError):
        pass
    finally:
        writer.close()


def _reply(body: bytes, status: bytes = b"200 OK", content_type: bytes = b"text/plain") -> bytes:
    return (b"HTTP/1.1 " + status + b"\r\nContent-Type: " + content_type
            + b"\r\nContent-Length: %d\r\nConnection: close\r\n\r\n" % len(body) + body)


class Lab:
    """Start with `async with Lab() as lab:`; lab.proxy(...) adds a proxy and returns its "ip:port"."""

    def __init__(self):
        self.exit_ips: Dict[int, str] = {}  # local port of a proxy's upstream connection -> that proxy's exit IP
        self.servers: List[asyncio.AbstractServer] = []
        self._handlers: Set[asyncio.Task] = set()  # running connection handlers, held so they aren't collected
        self.confirm_down = False  # the second target stops answering (directly and through proxies)
        self.page = PAGE           # what /html returns at its source
        self.https_status = b"200 OK"  # what the TLS target answers with
        self.judge_port = self.confirm_port = self.tls_port = self.untrusted_port = 0

    async def __aenter__(self) -> "Lab":
        self.judge_port = await self._listen(self._judge)
        self.confirm_port = await self._listen(self._confirm)
        self.tls_port = await self._listen(self._tls_judge, _context("localhost-cert.pem", "localhost-key.pem"))
        self.untrusted_port = await self._listen(self._judge, _context("untrusted-cert.pem", "untrusted-key.pem"))
        return self

    async def __aexit__(self, *exc) -> None:
        for server in self.servers:
            server.close()
        for server in self.servers:
            await server.wait_closed()

    async def _listen(self, handler, context: Optional[ssl.SSLContext] = None, port: int = 0) -> int:
        async def held(reader, writer) -> None:
            # Python 3.9/3.10 keep no reference to a start_server handler task: the garbage collector could end
            # one mid-answer ("Task was destroyed but it is pending!") and the checker saw an empty reply
            task = asyncio.current_task()
            self._handlers.add(task)
            try:
                await handler(reader, writer)
            finally:
                self._handlers.discard(task)

        server = await asyncio.start_server(held, "127.0.0.1", port, ssl=context)
        self.servers.append(server)
        return server.sockets[0].getsockname()[1]

    # ------------------------------------------------------------------ targets

    def _seen(self, writer) -> str:
        return self.exit_ips.get(writer.get_extra_info("peername")[1], OWN_IP)

    async def _judge(self, reader, writer) -> None:
        try:
            await reader.readuntil(b"\r\n\r\n")
            writer.write(_reply(self._seen(writer).encode() + b"\n"))
            await writer.drain()
        except (ConnectionError, OSError, asyncio.IncompleteReadError):
            pass
        finally:
            writer.close()

    async def _tls_judge(self, reader, writer) -> None:
        try:
            await reader.readuntil(b"\r\n\r\n")
            ok = self.https_status == b"200 OK"
            writer.write(_reply(self._seen(writer).encode() + b"\n" if ok else b"busy", self.https_status))
            await writer.drain()
        except (ConnectionError, OSError, asyncio.IncompleteReadError):
            pass
        finally:
            writer.close()

    async def stop_https(self) -> None:
        """The TLS target goes away: nothing listens on its port any more."""
        server = self.servers[2]
        server.close()
        await server.wait_closed()

    async def _confirm(self, reader, writer) -> None:
        try:
            head = await reader.readuntil(b"\r\n\r\n")
            if self.confirm_down:
                return
            path = head.split()[1]
            if path == b"/get":
                lines = head.decode("latin-1").split("\r\n")[1:]
                headers = dict(line.split(": ", 1) for line in lines if ": " in line)
                body = json.dumps({"origin": self._seen(writer), "headers": headers, "url": "lab"}).encode()
                writer.write(_reply(body, content_type=b"application/json"))
            elif path == b"/html":
                writer.write(_reply(self.page, content_type=b"text/html"))
            else:
                writer.write(_reply(b"", b"404 Not Found"))
            await writer.drain()
        except (ConnectionError, OSError, asyncio.IncompleteReadError):
            pass
        finally:
            writer.close()

    # ------------------------------------------------------------------ proxies

    async def proxy(self, exit_ip: str, *, second_exit_ip: str = "", rewrite: Optional[Callable[[bytes], bytes]] = None,
                    only_first_target: bool = False, no_connect: bool = False, breaks_tls: bool = False,
                    answers_after: float = 0.0, garbage: bool = False, adds_header: str = "",
                    port: int = 0) -> str:
        """An HTTP proxy that forwards to the lab's targets, with one flaw at most:

        second_exit_ip     the second target sees another address (a rotating or chained exit)
        rewrite            changes the body of /html on the way back
        only_first_target  answers the first check and refuses everything else
        no_connect         refuses CONNECT (no HTTPS)
        breaks_tls         answers TLS inside the tunnel with a certificate of its own
        answers_after      waits this many seconds before doing anything
        garbage            answers every request with a page of its own
        adds_header        a header line it adds to forwarded requests (e.g. "X-Forwarded-For: 203.0.113.1")
        """
        async def handle(reader, writer) -> None:
            try:
                head = await reader.readuntil(b"\r\n\r\n")
                if answers_after:
                    await asyncio.sleep(answers_after)
                method, url, rest = head.split(b" ", 2)
                if garbage:
                    writer.write(_reply(b"<html><body>Welcome to nginx!</body></html>", content_type=b"text/html"))
                    await writer.drain()
                    return
                if method == b"CONNECT":
                    port = int(url.rsplit(b":", 1)[1])
                    if no_connect or only_first_target:
                        writer.write(_reply(b"", b"405 Method Not Allowed"))
                        await writer.drain()
                        return
                    up_reader, up_writer = await self._upstream(self.untrusted_port if breaks_tls else port, exit_ip)
                    writer.write(b"HTTP/1.1 200 Connection established\r\n\r\n")
                    await writer.drain()
                    await asyncio.gather(_pipe(reader, up_writer), _pipe(up_reader, writer))
                    return
                hostport, _, path = url.decode().split("://", 1)[1].partition("/")
                port = int(hostport.partition(":")[2] or 80)
                if only_first_target and port != self.judge_port:
                    writer.write(_reply(b"", b"400 Bad Request"))
                    await writer.drain()
                    return
                seen_as = second_exit_ip if second_exit_ip and port == self.confirm_port else exit_ip
                up_reader, up_writer = await self._upstream(port, seen_as)
                extra = (adds_header + "\r\n").encode() if adds_header else b""
                up_writer.write(method + b" /" + path.encode() + b" " + rest[:-2] + extra + b"\r\n")
                await up_writer.drain()
                answer = await up_reader.read(-1)  # the targets close after one answer
                up_writer.close()
                if rewrite and path == "html":
                    answer_head, _, body = answer.partition(b"\r\n\r\n")
                    answer = _reply(rewrite(body), content_type=b"text/html") if answer_head else answer
                writer.write(answer)
                await writer.drain()
            except (ConnectionError, OSError, asyncio.IncompleteReadError, ValueError):
                pass
            finally:
                writer.close()

        return f"127.0.0.1:{await self._listen(handle, port=port)}"

    async def _upstream(self, port: int, exit_ip: str):
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        self.exit_ips[writer.get_extra_info("sockname")[1]] = exit_ip
        return reader, writer

    async def closed_port(self) -> str:
        """An address nothing listens on."""
        server = await asyncio.start_server(lambda r, w: None, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        server.close()
        await server.wait_closed()
        return f"127.0.0.1:{port}"

    # ------------------------------------------------------------------ a checker that uses the lab

    async def reference(self) -> Optional[bytes]:
        """The hash of /html asked directly – None while the target is down."""
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", self.confirm_port)
            writer.write(b"GET /html HTTP/1.1\r\nHost: localhost\r\n\r\n")
            await writer.drain()
            body = (await reader.read(-1)).partition(b"\r\n\r\n")[2]
            writer.close()
        except (ConnectionError, OSError):
            return None
        return ck.page_hash(body) if body else None

    async def checker(self, timeout: float = 2.0, confirm: bool = True, reference: bool = True,
                      https_test: bool = True, controls: bool = True) -> ck.Checker:
        c = ck.Checker("127.0.0.1", {OWN_IP}, timeout=timeout, connect_timeout=timeout,
                       confirm_ip="127.0.0.1" if confirm else None, https_test=https_test,
                       judge=Judge("localhost", "/", self.judge_port),
                       integrity_reference=await self.reference() if reference and confirm else None,
                       confirm_host="localhost", confirm_port=self.confirm_port)
        c.https_port, c.tls_context, c.reserved_exit_ips_ok = self.tls_port, client_context(), True
        if controls:
            c.controls = {
                CONFIRM: lambda: ck.probe_confirm_target("127.0.0.1", 1.0, self.confirm_port),
                CONTENT: self.reference,
                HTTPS: lambda: ck.probe_https_target("localhost", "127.0.0.1", c.https_port, c.tls_context, 1.0,
                                                     request=c.request),
            }
        return c


class LabThread:
    """The lab on a loop of its own in a background thread – for code that starts its own event loops
    (the command line does, once per step): `with LabThread() as lab: proxy = lab.run(lab.proxy(...))`."""

    def __enter__(self) -> "LabThread":
        import threading

        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.loop.run_forever, name="proxy-lab", daemon=True)
        self.thread.start()
        self.lab = self.run(Lab().__aenter__())
        return self

    def run(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, self.loop).result(10)

    def __getattr__(self, name):
        return getattr(self.lab, name)

    def __exit__(self, *exc) -> None:
        self.run(self.lab.__aexit__(None, None, None))
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(5)
        self.loop.close()
