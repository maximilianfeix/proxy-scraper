"""Resource limits of the rotating server: slow uploads, too many clients, cancellation and endless interim
responses must not tie up handlers or proxy reservations."""

import asyncio
import base64

import pytest

from proxyscraper.checker import CheckResult
from proxyscraper.server import ProxyPool, RotatingServer
from proxyscraper.server.http import ResponseScreen

from .fakes import echo_server, http_forward_proxy, serve


class OrderedPool(ProxyPool):
    def pick(self, exclude, tls=False, **_):
        return next((e for e in self.usable if e.result.key not in exclude), None)


def result(port):
    return CheckResult(f"http 127.0.0.1:{port}", "http", f"127.0.0.1:{port}", 100, "9.9.9.9", https=True)


async def settle(server, rounds=40):
    """Give cancelled handlers a moment to run their cleanup."""
    for _ in range(rounds):
        if not server._handlers:
            break
        await asyncio.sleep(0.01)


# ------------------------------------------------------------------ partial uploads and the client cap

def test_partial_small_body_does_not_hold_the_handler():
    async def go():
        rotating = RotatingServer(OrderedPool([result(1)]), port=0, timeout=0.05)
        await rotating.start()
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", rotating.port)
            writer.write(b"POST http://127.0.0.1:9/x HTTP/1.1\r\nHost: 127.0.0.1:9\r\nContent-Length: 10\r\n\r\nA")
            await writer.drain()
            await asyncio.sleep(0.2)
            alive = len(rotating._handlers)
            answer = await asyncio.wait_for(reader.read(65536), 1)
            writer.close()
            return alive, answer, rotating.stats.active
        finally:
            await rotating.close()

    alive, answer, active = asyncio.run(go())
    assert alive == 0 and active == 0
    assert answer.startswith(b"HTTP/1.1 408")


def test_stalled_streamed_upload_ends_the_exchange():
    """A large (streamed) body whose client goes quiet: the upload stops after the idle deadline, the
    upstream is released and the handler ends – the target never waits forever for the rest."""
    async def go():
        proxy_srv, proxy_port = await serve(http_forward_proxy)
        sink_srv, sink_port = await serve(sink_server)
        pool = OrderedPool([result(proxy_port)])
        rotating = RotatingServer(pool, port=0, timeout=0.1)
        await rotating.start()
        try:
            _reader, writer = await asyncio.open_connection("127.0.0.1", rotating.port)
            writer.write(f"POST http://127.0.0.1:{sink_port}/x HTTP/1.1\r\nHost: x\r\n"
                         f"Content-Length: {5 * 1024 * 1024}\r\n\r\n".encode() + b"y" * 1000)
            await writer.drain()
            await asyncio.sleep(0.6)
            state = len(rotating._handlers), pool.entries[0].active
            writer.close()
            return state
        finally:
            await rotating.close()
            proxy_srv.close()
            sink_srv.close()

    assert asyncio.run(go()) == (0, 0)


async def sink_server(reader, writer):
    """A target that reads forever and never answers on its own."""
    while await reader.read(65536):
        pass
    writer.close()


def test_too_many_clients_get_503():
    async def go():
        rotating = RotatingServer(OrderedPool([result(1)]), port=0, timeout=2, max_clients=2)
        await rotating.start()
        try:
            idle = [await asyncio.open_connection("127.0.0.1", rotating.port) for _ in range(2)]
            await asyncio.sleep(0.05)
            reader, writer = await asyncio.open_connection("127.0.0.1", rotating.port)
            answer = await asyncio.wait_for(reader.read(65536), 1)
            writer.close()
            for _, w in idle:
                w.close()
            await asyncio.sleep(0.05)
            # a slot is free again: the next client is served normally (here: a 400 for garbage)
            reader, writer = await asyncio.open_connection("127.0.0.1", rotating.port)
            writer.write(b"nonsense\r\n\r\n")
            after = await asyncio.wait_for(reader.read(65536), 1)
            writer.close()
            return answer, after, rotating.stats.active
        finally:
            await rotating.close()

    answer, after, _active = asyncio.run(go())
    assert answer.startswith(b"HTTP/1.1 503") and b"Connection: close" in answer
    assert after.startswith(b"HTTP/1.1 400")


def test_long_tunnels_are_not_cut_by_the_upload_deadline():
    """CONNECT tunnels have no idle or lifetime limit – a quiet SSH or WebSocket session stays open."""
    async def go():
        echo_srv, echo_port = await serve(echo_server)
        proxy_srv, proxy_port = await serve(http_forward_proxy)
        rotating = RotatingServer(OrderedPool([result(proxy_port)]), port=0, timeout=0.05)
        await rotating.start()
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", rotating.port)
            writer.write(f"CONNECT 127.0.0.1:{echo_port} HTTP/1.1\r\n\r\n".encode())
            await writer.drain()
            await reader.readuntil(b"\r\n\r\n")
            writer.write(b"eins\n")
            first = await asyncio.wait_for(reader.readline(), 2)
            await asyncio.sleep(0.3)  # six times the timeout without a byte
            writer.write(b"zwei\n")
            second = await asyncio.wait_for(reader.readline(), 2)
            writer.write(b"bye\n")
            writer.close()
            return first, second
        finally:
            await rotating.close()
            echo_srv.close()
            proxy_srv.close()

    assert asyncio.run(go()) == (b"echo: eins\n", b"echo: zwei\n")


# ------------------------------------------------------------------ cancellation keeps the pool counters right

def session_auth(name):
    return b"Proxy-Authorization: Basic " + base64.b64encode(f"session-{name}:x".encode()) + b"\r\n"


def phase_proxy(phase, reached):
    """An HTTP proxy that stops at one phase of the exchange and signals when it got there."""
    async def handler(reader, writer):
        head = await reader.readuntil(b"\r\n\r\n")
        if phase == "connect":  # never answers the CONNECT
            reached.set()
            await reader.read()
            return
        if head.startswith(b"CONNECT"):
            writer.write(b"HTTP/1.1 200 Connection established\r\n\r\n")
            await writer.drain()
            if phase == "first-packet":
                reached.set()  # the rotating server now waits for the client's first packet
            first = await reader.read(65536)
        else:
            first = head
        if phase == "exchange" and first:
            reached.set()  # the first packet arrived, the answer never comes
        if phase == "relay":
            writer.write(b"\x16\x03\x03\x00\x04helo" if first[:1] == b"\x16" else b"HTTP/1.1 200 OK\r\n\r\npart")
            await writer.drain()
            reached.set()
        await reader.read()
        writer.close()
    return handler


@pytest.mark.parametrize("phase, tunnel", [
    ("connect", True), ("first-packet", True), ("exchange", True), ("relay", True),
    ("exchange", False), ("relay", False),
])
@pytest.mark.parametrize("how", ["abort_session", "close"])
def test_cancellation_releases_the_upstream(phase, tunnel, how):
    async def go():
        reached = asyncio.Event()
        proxy_srv, proxy_port = await serve(phase_proxy(phase, reached))
        pool = OrderedPool([result(proxy_port)])
        rotating = RotatingServer(pool, port=0, timeout=5)
        await rotating.start()
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", rotating.port)
            if tunnel:
                writer.write(b"CONNECT 127.0.0.1:443 HTTP/1.1\r\n" + session_auth("s1") + b"\r\n")
                if phase != "first-packet":
                    await writer.drain()
                    if phase != "connect":
                        await reader.readuntil(b"\r\n\r\n")
                    writer.write(b"\x16\x03\x01\x00\x05hello")
            else:
                writer.write(b"GET http://127.0.0.1:80/ HTTP/1.1\r\nHost: 127.0.0.1\r\n" + session_auth("s1")
                             + b"\r\n")
            await writer.drain()
            await asyncio.wait_for(reached.wait(), 3)
            await asyncio.sleep(0.05)
            assert pool.entries[0].active == 1
            if how == "abort_session":
                assert rotating.abort_session("s1") == 1
                await settle(rotating)
            else:
                await rotating.close()
            state = len(rotating._handlers), rotating.stats.active, pool.entries[0].active
            writer.close()
            return state
        finally:
            await rotating.close()
            proxy_srv.close()

    assert asyncio.run(go()) == (0, 0, 0)


# ------------------------------------------------------------------ interim responses

def test_response_screen_caps_the_number_of_interim_responses():
    screen = ResponseScreen()
    verdict = None
    for _ in range(1000):
        _out, verdict = screen.feed(b"HTTP/1.1 103 Early Hints\r\nLink: </a.css>; rel=preload\r\n\r\n")
        if verdict is not None:
            break
    assert verdict == "407"  # "don't use this upstream" – same as a huge interim response


def test_response_screen_still_passes_a_few_interim_responses():
    screen = ResponseScreen()
    out, verdict = screen.feed(b"HTTP/1.1 100 Continue\r\n\r\nHTTP/1.1 103 Early Hints\r\nLink: <x>\r\n\r\n"
                               b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n")
    assert verdict == "ok" and out.endswith(b"200 OK\r\nContent-Length: 0\r\n\r\n") and out.count(b"HTTP/1.1") == 3


def endless_interim_proxy(delay):
    async def handler(reader, writer):
        await reader.readuntil(b"\r\n\r\n")
        try:
            while True:
                writer.write(b"HTTP/1.1 102 Processing\r\n\r\n")
                await writer.drain()
                await asyncio.sleep(delay)
        except (ConnectionError, OSError):
            pass
    return handler


@pytest.mark.parametrize("delay", [0.0, 0.03])
def test_endless_interim_responses_end_in_502(delay):
    """Many small interim responses (fast: count cap; slow, each within the per-read timeout: total
    deadline) never become a final response – the client gets a 502 in bounded time."""
    async def go():
        proxy_srv, proxy_port = await serve(endless_interim_proxy(delay))
        pool = OrderedPool([result(proxy_port)])
        rotating = RotatingServer(pool, port=0, timeout=0.3)
        await rotating.start()
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", rotating.port)
            writer.write(b"GET http://127.0.0.1:80/ HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n")
            await writer.drain()
            answer = await asyncio.wait_for(reader.read(65536), 3)
            writer.close()
            return answer, pool
        finally:
            await rotating.close()
            proxy_srv.close()

    answer, pool = asyncio.run(go())
    assert answer.startswith(b"HTTP/1.1 502")
    assert pool.entries[0].fail == 1 and pool.entries[0].active == 0
