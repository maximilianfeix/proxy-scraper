"""Incremental decoder for HTTP/1.1 chunked transfer coding (RFC 9112, section 7.1).

Shared by netio.read_response and the checker's small response reader: both feed it whatever arrived and
stop reading as soon as the 0-chunk and its trailers are complete – a keep-alive server or proxy doesn't
close the connection after a complete answer, so waiting for EOF would only run into the timeout.
Only the framing lives here; what a caller accepts (status, size, content) stays with the caller.
"""

from __future__ import annotations

import re

_SIZE_RE = re.compile(rb"[0-9A-Fa-f]{1,16}")  # strict: int(x, 16) would also take "-3", "+3", "1_0", " 3"
MAX_LINE = 8192  # a chunk-size line or one trailer line
MAX_TRAILERS = 64 * 1024


class FramingError(ConnectionError):
    """A response whose framing is broken, too large or cut off."""


class ChunkedDecoder:
    """feed() the bytes after the header block as they arrive; it returns True once the body is complete.

    Bytes after the end (a pipelined response, garbage) are not part of the body and are ignored.
    Raises FramingError on malformed framing or a body larger than `limit`; call finish() at EOF to turn
    a cut-off body into an error as well.
    """

    def __init__(self, limit: int):
        self.limit = limit
        self.body = bytearray()
        self.done = False
        self._buf = bytearray()
        self._state = "size"  # size -> data -> crlf -> size ... -> trailer -> done
        self._left = 0
        self._trailer_bytes = 0

    def feed(self, data: bytes) -> bool:
        if self.done:
            return True
        self._buf += data
        while not self.done:
            if self._state == "data":
                if not self._buf:
                    break
                take = min(self._left, len(self._buf))
                self.body += self._buf[:take]
                del self._buf[:take]
                self._left -= take
                if self._left:
                    break
                self._state = "crlf"
            elif self._state == "crlf":
                if len(self._buf) < 2:
                    break
                if self._buf[:2] != b"\r\n":
                    raise FramingError("chunk longer than announced")
                del self._buf[:2]
                self._state = "size"
            else:  # "size" or "trailer": both are lines
                line = self._line()
                if line is None:
                    break
                if self._state == "size":
                    self._size_line(line)
                elif line:
                    self._trailer_bytes += len(line) + 2
                    if self._trailer_bytes > MAX_TRAILERS:
                        raise FramingError("trailers too large")
                else:
                    self.done = True  # the empty line after the last chunk (and its trailers)
        return self.done

    def finish(self) -> bytes:
        """The connection ended: the body, or FramingError if it was cut off."""
        if not self.done:
            raise FramingError("chunked body cut off")
        return bytes(self.body)

    def _line(self):
        end = self._buf.find(b"\r\n")
        if end < 0:
            if len(self._buf) > MAX_LINE:
                raise FramingError("chunk line too long")
            return None
        if end > MAX_LINE:
            raise FramingError("chunk line too long")
        line = bytes(self._buf[:end])
        del self._buf[:end + 2]
        return line

    def _size_line(self, line: bytes) -> None:
        size_text = line.split(b";", 1)[0].rstrip(b" \t")  # chunk extensions are ignored
        if not _SIZE_RE.fullmatch(size_text):
            raise FramingError("invalid chunk size")
        size = int(size_text, 16)
        if size == 0:
            self._state = "trailer"
            return
        if len(self.body) + size > self.limit:
            raise FramingError("response too large")
        self._left = size
        self._state = "data"
