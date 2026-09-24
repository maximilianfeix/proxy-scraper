import io

import pytest
from rich.console import Console

from proxyscraper import app
from proxyscraper.checker import CheckResult
from proxyscraper.options import RunOptions
from proxyscraper.ui import widgets


def record(monkeypatch, width=80):
    console = Console(width=width, file=io.StringIO(), color_system=None, record=True)
    monkeypatch.setattr(widgets, "console", console)
    return console


def test_section_frames_info_and_notes(monkeypatch):
    console = record(monkeypatch)
    widgets.section("Vorbereitung")
    widgets.info("Deine IP", "203.0.113.7")
    widgets.note("Achtung")
    widgets.section_end()
    widgets.info("Danach", "ohne Rahmen")
    lines = console.export_text().splitlines()
    assert lines[0].startswith("  ╭─ Vorbereitung ─")
    assert lines[1].startswith("  │  Deine IP") and lines[2].startswith("  │  ⚠ Achtung")
    assert lines[3] == "  ╰─" and lines[4].startswith("  Danach")


def test_gutter_color_does_not_bleed_into_values(monkeypatch):
    """Die dunkle Rahmenfarbe darf nur das Rahmenzeichen färben, nicht den Wert dahinter."""
    record(monkeypatch)
    widgets.section("X")
    line = widgets._gutter()
    line.append("wert")
    assert line.style == "" and line.spans[0].end == len("  │  ")
    widgets.section_end()


def test_banner_shows_version():
    from proxyscraper import __version__

    console = Console(width=80, file=io.StringIO(), color_system=None, record=True)
    console.print(widgets.banner())
    assert f"v{__version__}" in console.export_text()


def test_next_steps():
    fast = CheckResult("socks5 1.2.3.4:1080", "socks5", "1.2.3.4:1080", 90, "9.9.9.9")
    slow = CheckResult("http 5.6.7.8:80", "http", "5.6.7.8:80", 900, "9.9.9.9")
    steps = dict(app.next_steps(RunOptions(), [slow, fast]))
    assert steps["Schnellsten testen"] == "curl -x socks5h://1.2.3.4:1080 https://api.ipify.org"
    assert steps["Als Proxy-Server"].endswith("--recheck --serve")
    assert "Als Proxy-Server" not in dict(app.next_steps(RunOptions(serve=8899), [fast]))  # läuft ja schon
    assert list(dict(app.next_steps(RunOptions(), []))) == ["Später neu prüfen"]


@pytest.mark.parametrize("checkout, program", [(True, "python3 proxy_scraper.py"), (False, "proxy-scraper")])
def test_next_steps_use_the_right_command(monkeypatch, checkout, program):
    monkeypatch.setattr(app, "is_checkout", lambda: checkout)
    fast = CheckResult("http 1.2.3.4:80", "http", "1.2.3.4:80", 90, "9.9.9.9")
    steps = dict(app.next_steps(RunOptions(), [fast]))
    assert steps["Schnellsten testen"] == "curl -x http://1.2.3.4:80 https://api.ipify.org"
    assert steps["Als Proxy-Server"] == f"{program} --recheck --serve"
    assert steps["Später neu prüfen"] == f"{program} --recheck"
