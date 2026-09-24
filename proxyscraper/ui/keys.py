"""Einzelne Tastendrücke lesen – ohne Enter, ohne Zusatzbibliothek, auf Unix und Windows.

Liefert Namen wie "up", "down", "enter", "space", "esc", "backspace" oder das Zeichen selbst.
"""

from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from typing import Callable, Iterator

from ..compat import IS_WINDOWS

# Escape-Sequenzen der Pfeiltasten (xterm und "application mode")
_ESCAPES = {
    "[A": "up", "[B": "down", "[C": "right", "[D": "left",
    "OA": "up", "OB": "down", "OC": "right", "OD": "left",
    "[H": "home", "[F": "end", "[5~": "pageup", "[6~": "pagedown",
}
_WINDOWS_SPECIAL = {
    "H": "up", "P": "down", "M": "right", "K": "left",
    "G": "home", "O": "end", "I": "pageup", "Q": "pagedown",
}
_SIMPLE = {
    "\r": "enter", "\n": "enter", " ": "space", "\t": "tab",
    "\x7f": "backspace", "\x08": "backspace", "\x03": "ctrl-c",
}


def is_interactive() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def decode(seq: str) -> str:
    """Rohe Zeichenfolge eines Tastendrucks -> Tastenname."""
    if seq.startswith("\x1b"):
        return _ESCAPES.get(seq[1:], "esc")
    return _SIMPLE.get(seq, seq)


@contextmanager
def raw_keys() -> Iterator[Callable[[], str]]:
    """Terminal in den Rohmodus schalten; liefert eine Funktion, die den nächsten Tastendruck liest."""
    if IS_WINDOWS:
        import msvcrt

        def read_windows() -> str:
            ch = msvcrt.getwch()
            if ch in ("\x00", "\xe0"):  # Sondertaste: zweites Zeichen sagt welche
                return _WINDOWS_SPECIAL.get(msvcrt.getwch(), "")
            if ch == "\x1b":
                return "esc"
            return decode(ch)

        yield read_windows
        return

    import select
    import termios
    import tty

    fd = sys.stdin.fileno()
    saved = termios.tcgetattr(fd)

    def read_unix() -> str:
        ch = os.read(fd, 1).decode("utf-8", "ignore")
        if ch != "\x1b":
            return decode(ch)
        # ESC allein oder Beginn einer Sequenz? Kurz warten, ob noch etwas kommt
        seq = ch
        while select.select([fd], [], [], 0.03)[0]:
            seq += os.read(fd, 1).decode("utf-8", "ignore")
            if seq[-1].isalpha() or seq[-1] == "~":
                break
        return decode(seq)

    try:
        tty.setcbreak(fd)  # Strg+C bleibt ein Signal – Abbrechen funktioniert wie gewohnt
        yield read_unix
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, saved)
