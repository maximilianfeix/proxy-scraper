"""Plattformunterschiede an einer Stelle: Datei-Limits, Strg+C, Konsolen-Kodierung.

Auf Windows gibt es kein `resource`-Modul und kein `loop.add_signal_handler`; dort laufen
asyncio-Programme auf dem ProactorEventLoop (IOCP), der kein select()-Limit für Sockets hat.
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
    """Erlaubte offene Dateien/Sockets hochsetzen; gibt das tatsächliche Limit zurück."""
    if resource is None:
        # Kein RLIMIT_NOFILE: Der ProactorEventLoop begrenzt Sockets nicht über ein solches Limit
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
    """Strg+C ruft `callback` in der Event-Loop auf, statt KeyboardInterrupt zu werfen.

    Unix: loop.add_signal_handler. Windows kennt das nicht – dort ein klassischer
    signal-Handler, der den Callback threadsicher in die Loop reicht.
    Danach ist in beiden Fällen wieder der vorherige Handler aktiv.
    """
    previous = signal.getsignal(signal.SIGINT)
    try:
        loop.add_signal_handler(signal.SIGINT, callback)
    except (NotImplementedError, RuntimeError):
        try:
            signal.signal(signal.SIGINT, lambda signum, frame: loop.call_soon_threadsafe(callback))
        except ValueError:  # nicht im Haupt-Thread -> Strg+C bleibt Standardverhalten
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
        # remove_signal_handler() setzt SIGINT fest auf default_int_handler zurück,
        # nicht auf einen vorher installierten Handler
        loop.remove_signal_handler(signal.SIGINT)
        if previous is not None:
            signal.signal(signal.SIGINT, previous)


def ensure_utf8_output() -> None:
    """Ausgabe auf UTF-8 umstellen, falls die Konsole etwas anderes nutzt (z. B. cp1252 unter Windows).

    Sonst können Zeichen wie ✔ oder ▁ beim Umleiten in eine Datei einen UnicodeEncodeError auslösen.
    """
    for stream in (sys.stdout, sys.stderr):
        encoding = (getattr(stream, "encoding", "") or "").lower().replace("-", "")
        if encoding != "utf8" and hasattr(stream, "reconfigure"):
            with contextlib.suppress(ValueError, OSError):  # z. B. bereits geschlossener oder fremder Stream
                stream.reconfigure(encoding="utf-8", errors="replace")
