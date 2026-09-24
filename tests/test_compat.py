import asyncio
import io
import signal
import sys

import pytest

from proxyscraper import compat


def test_raise_fd_limit_without_resource_module(monkeypatch):
    monkeypatch.setattr(compat, "resource", None)  # so sieht es unter Windows aus
    assert compat.raise_fd_limit(2512) == 2512


@pytest.mark.skipif(compat.resource is None, reason="nur mit resource-Modul")
def test_raise_fd_limit_returns_usable_limit():
    assert compat.raise_fd_limit(1024) >= 256


def _interrupt_calls_callback(patch_loop=None) -> list:
    calls = []

    async def go():
        loop = asyncio.get_running_loop()
        if patch_loop:
            patch_loop(loop)
        with compat.on_interrupt(loop, lambda: calls.append("stop")):
            signal.raise_signal(signal.SIGINT)
            for _ in range(20):
                if calls:
                    break
                await asyncio.sleep(0.01)

    asyncio.run(go())
    return calls


def test_on_interrupt_fallback_without_add_signal_handler():
    # Windows: add_signal_handler fehlt -> klassischer signal-Handler muss einspringen
    def no_signal_handlers(loop):
        def raise_not_implemented(*args, **kwargs):
            raise NotImplementedError

        loop.add_signal_handler = raise_not_implemented

    before = signal.getsignal(signal.SIGINT)
    assert _interrupt_calls_callback(no_signal_handlers) == ["stop"]
    assert signal.getsignal(signal.SIGINT) is before  # vorheriger Handler ist wiederhergestellt


@pytest.mark.skipif(sys.platform == "win32", reason="add_signal_handler gibt es nur auf Unix")
def test_on_interrupt_with_loop_signal_handler():
    assert _interrupt_calls_callback() == ["stop"]


def test_ensure_utf8_output_reconfigures_legacy_encoding(monkeypatch):
    raw = io.BytesIO()
    legacy = io.TextIOWrapper(raw, encoding="cp1252")
    monkeypatch.setattr(sys, "stdout", legacy)
    compat.ensure_utf8_output()
    print("✔ ▁▂▃")  # in cp1252 nicht darstellbar
    legacy.flush()
    assert raw.getvalue().decode("utf-8").strip() == "✔ ▁▂▃"
