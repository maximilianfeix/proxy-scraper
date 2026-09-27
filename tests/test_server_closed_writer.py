"""uvloop reports a write to a closed connection as RuntimeError, not ConnectionError. The relay has to treat it
like any other hang-up – otherwise the handler dies before the failure is counted (seen as a flaky test)."""

import asyncio

from proxyscraper.server.core import RotatingServer
from proxyscraper.server.pool import ProxyPool


class ClosedWriter:
    def write(self, data):
        raise RuntimeError("unable to perform operation on <TCPTransport closed=True>; the handler is closed")

    async def drain(self):
        pass

    def write_eof(self):
        raise RuntimeError("closed")

    def close(self):
        pass


def reader_with(data: bytes):
    r = asyncio.StreamReader()
    r.feed_data(data)
    r.feed_eof()
    return r


def server():
    return RotatingServer(ProxyPool([]), port=0)


def test_send_body_to_a_closed_upstream_is_a_hang_up():
    async def go():
        return await server()._send_body(reader_with(b"x" * 100), ClosedWriter(), 100)
    assert asyncio.run(go()) == 100  # no exception: what was read is counted, the relay ends normally


def test_pipe_into_a_closed_client_is_a_hang_up():
    async def go():
        return await server()._pipe(reader_with(b"HTTP/1.1 200 OK\r\n\r\nhi"), ClosedWriter(), up=False)
    assert asyncio.run(go()) == 21  # the upstream did answer – that's what counts for the proxy


def test_a_closed_client_before_the_final_answer_is_a_failure():
    async def go():
        return await server()._pipe(reader_with(b""), ClosedWriter(), up=False, reject_proxy_auth=True)
    assert asyncio.run(go()) == -1


def test_first_packet_to_a_closed_proxy_means_try_the_next_one():
    async def go():
        return await server()._exchange(reader_with(b""), ClosedWriter(), b"GET / HTTP/1.1\r\n\r\n")
    assert asyncio.run(go()) is None


def test_giving_up_on_a_proxy_closes_its_connection():
    class Entry:
        active = 1

    class Writer:
        closed = False

        def close(self):
            self.closed = True

    s, entry, writer = server(), Entry(), Writer()
    s.pool.report = lambda e, ok: None
    s._give_up(entry, writer)
    assert entry.active == 0 and writer.closed
