"""Platform differences in one place: file limits, Ctrl+C, console encoding.

Windows has no `resource` module and no `loop.add_signal_handler`; asyncio programs run on the
ProactorEventLoop (IOCP) there, which has no select() limit for sockets.
"""

from __future__ import annotations

import asyncio
import contextlib
import signal
import sys
from contextlib import contextmanager
from typing import Callable, Iterator

IS_WINDOWS = sys.platform == "win32"

try:
    import resource
except ImportError:  # Windows
    resource = None


def raise_fd_limit(wanted: int) -> int:
    """Raise the allowed open files/sockets; returns the actual limit."""
    if resource is None:
        # no RLIMIT_NOFILE: the ProactorEventLoop doesn't limit sockets through such a limit
        return wanted
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    target = wanted if hard == resource.RLIM_INFINITY else min(wanted, hard)
    if soft < target:
        for t in (target, 10240, 4096):
            try:
                resource.setrlimit(resource.RLIMIT_NOFILE, (t, hard))
                return t
            except (ValueError, OSError):
                continue
    return resource.getrlimit(resource.RLIMIT_NOFILE)[0]


@contextmanager
def on_interrupt(loop: asyncio.AbstractEventLoop, callback: Callable[[], None]) -> Iterator[None]:
    """Ctrl+C calls `callback` in the event loop instead of raising KeyboardInterrupt.

    Unix: loop.add_signal_handler. Windows doesn't have that – there a classic
    signal handler passes the callback into the loop thread-safely.
    Afterwards the previous handler is active again in both cases.
    """
    previous = signal.getsignal(signal.SIGINT)
    try:
        loop.add_signal_handler(signal.SIGINT, callback)
    except (NotImplementedError, RuntimeError):
        try:
            signal.signal(signal.SIGINT, lambda signum, frame: loop.call_soon_threadsafe(callback))
        except ValueError:  # not in the main thread -> Ctrl+C keeps its default behavior
            yield
            return
        try:
            yield
        finally:
            if previous is not None:
                signal.signal(signal.SIGINT, previous)
        return
    try:
        yield
    finally:
        # remove_signal_handler() resets SIGINT to default_int_handler,
        # not to a handler that was installed before
        loop.remove_signal_handler(signal.SIGINT)
        if previous is not None:
            signal.signal(signal.SIGINT, previous)


def ensure_utf8_output() -> None:
    """Switch output to UTF-8 if the console uses something else (e.g. cp1252 on Windows).

    Otherwise characters like ✔ or ▁ can raise a UnicodeEncodeError when redirecting to a file.
    """
    for stream in (sys.stdout, sys.stderr):
        encoding = (getattr(stream, "encoding", "") or "").lower().replace("-", "")
        if encoding != "utf8" and hasattr(stream, "reconfigure"):
            with contextlib.suppress(ValueError, OSError):  # e.g. an already closed or foreign stream
                stream.reconfigure(encoding="utf-8", errors="replace")
