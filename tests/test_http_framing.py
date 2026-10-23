"""Chunked responses end at the 0-chunk and its trailers – not at the end of the connection.

Keep-alive servers and proxies don't close after a complete chunked answer; reading to EOF ran into the
timeout although everything had arrived. Both readers (netio.read_response for sources/APIs, the checker's
small _read_http_200) parse the framing incrementally and reject broken or cut-off bodies.
"""

import asyncio

import pytest

from proxyscraper import checker, netio

HEAD = b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n"


def feed(parts, eof=False):
    """A StreamReader that gets `parts` one after the other (fragmented on the wire), EOF only if asked."""
    reader = asyncio.StreamReader()

    async def writer():
        for part in parts:
            reader.feed_data(part)
            await asyncio.sleep(0)
        if eof:
            reader.feed_eof()
    return reader, writer


def run_netio(parts, eof=False, timeout=1.0):
    async def go():
        reader, writer = feed(parts, eof)
        task = asyncio.ensure_future(writer())
        try:
            return await asyncio.wait_for(netio.read_response(reader), timeout)
        finally:
            await task
    return asyncio.run(go())


def run_checker(parts, eof=False, timeout=1.0):
    async def go():
        reader, writer = feed(parts, eof)
        task = asyncio.ensure_future(writer())
        try:
            return await asyncio.wait_for(checker._read_http_200(reader), timeout)
        finally:
            await task
    return asyncio.run(go())


def bytewise(data: bytes):
    return [data[i:i + 1] for i in range(len(data))]


COMPLETE = HEAD + b"3\r\nabc\r\n0\r\n\r\n"


def test_netio_complete_chunked_body_without_connection_close():
    status, _, body = run_netio([COMPLETE])  # no EOF: must not wait for one
    assert (status, body) == (200, b"abc")


def test_checker_complete_chunked_body_without_connection_close():
    assert run_checker([COMPLETE]) == b"abc"


@pytest.mark.parametrize("run", [run_netio, run_checker])
def test_fragmented_extensions_and_trailers(run):
    data = HEAD + b"3;name=value\r\nabc\r\nA ; x\r\n0123456789\r\n0\r\nX-Trailer: 1\r\nX-Other: 2\r\n\r\n"
    out = run(bytewise(data))
    body = out[2] if isinstance(out, tuple) else out
    assert body == b"abc0123456789"


def test_bytes_after_the_last_chunk_are_not_part_of_the_body():
    _, _, body = run_netio([COMPLETE + b"HTTP/1.1 200 OK\r\n"])
    assert body == b"abc"


@pytest.mark.parametrize("tail", [
    b"3\r\nab",              # cut off inside a chunk
    b"3\r\nabc\r\n",         # no 0-chunk
    b"3\r\nabc\r\n0\r\n",    # 0-chunk without the final empty line
])
def test_truncated_bodies_are_rejected(tail):
    with pytest.raises(ConnectionError):
        run_netio([HEAD + tail], eof=True)
    assert run_checker([HEAD + tail], eof=True) is None


@pytest.mark.parametrize("tail", [
    b"zz\r\nabc\r\n0\r\n\r\n",       # not hex
    b"-3\r\nabc\r\n0\r\n\r\n",       # a sign
    b"1_0\r\n" + b"x" * 16 + b"\r\n0\r\n\r\n",  # int() would take that
    b"3\r\nabcX\r\n0\r\n\r\n",       # chunk longer than announced
    b"\r\nabc\r\n0\r\n\r\n",         # no size at all
])
def test_malformed_bodies_are_rejected(tail):
    with pytest.raises(ConnectionError):
        run_netio([HEAD + tail], eof=True)
    assert run_checker([HEAD + tail], eof=True) is None


def test_oversize_chunked_bodies_are_rejected(monkeypatch):
    monkeypatch.setattr(netio, "MAX_BODY", 10)
    with pytest.raises(ConnectionError):
        run_netio([HEAD + b"b\r\n" + b"x" * 11 + b"\r\n0\r\n\r\n"])
    big = b"%x\r\n" % 20000 + b"x" * 20000 + b"\r\n0\r\n\r\n"
    assert run_checker([HEAD + big]) is None  # the checker reads at most 16 KiB


def test_an_endless_chunk_size_line_is_rejected():
    with pytest.raises(ConnectionError):
        run_netio([HEAD + b"1" * 100000])


def test_content_length_and_plain_bodies_still_work():
    _, _, body = run_netio([b"HTTP/1.1 200 OK\r\nContent-Length: 3\r\n\r\nabc"])
    assert body == b"abc"
    _, _, body = run_netio([b"HTTP/1.1 200 OK\r\n\r\nabc"], eof=True)
    assert body == b"abc"
    assert run_checker([b"HTTP/1.1 200 OK\r\nContent-Length: 3\r\n\r\nabc"]) == b"abc"
    assert run_checker([b"HTTP/1.1 404 Not Found\r\nTransfer-Encoding: chunked\r\n\r\n"]) is None


def test_a_header_value_mentioning_chunked_is_not_chunked_framing():
    data = b"HTTP/1.1 200 OK\r\nX-Note: chunked\r\nContent-Length: 3\r\n\r\nabc"
    assert run_checker([data]) == b"abc"
