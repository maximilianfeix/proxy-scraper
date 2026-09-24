"""Der Einrichtungsassistent als Tastenfolgen – ohne echtes Terminal."""

import io

import pytest
from rich.console import Console

from proxyscraper.cli import parse_args, wants_wizard
from proxyscraper.options import Filters, RunOptions
from proxyscraper.ui.keys import decode
from proxyscraper.ui.wizard import MultiStep, SummaryStep, Wizard


def press(wizard: Wizard, *keys: str) -> Wizard:
    for key in keys:
        wizard.handle(key)
    return wizard


def preset_index(wizard: Wizard, label: str) -> str:
    return str(next(i for i, o in enumerate(wizard.start.options, 1) if o.label.startswith(label)))


def test_default_preset_starts_immediately():
    w = press(Wizard(RunOptions()), "enter", "enter")  # "Alles finden" -> Übersicht -> Start
    assert w.result == RunOptions()


def test_web_preset():
    w = Wizard(RunOptions())
    press(w, preset_index(w, "Surfen"), "enter")
    assert w.result.types == ["http", "socks5"]
    assert w.result.filters == Filters(https_only=True, min_anonymity="anonymous", max_latency=3000)


def test_presets_keep_technical_options_from_command_line():
    w = Wizard(RunOptions(concurrency=500, timeout=5.0))
    press(w, preset_index(w, "Maximal anonym"), "enter")
    assert (w.result.concurrency, w.result.timeout, w.result.types) == (500, 5.0, ["socks5"])


def test_custom_walkthrough():
    w = Wizard(RunOptions())
    press(w, preset_index(w, "Eigene"))
    # Protokolle: SOCKS4 abwählen (Cursor steht auf HTTP)
    press(w, "down", "space", "enter")
    # Länder: DE und AT per Buchstabensprung anhaken
    press(w, "d", "space", "o", "space", "enter")
    press(w, "down", "down", "enter")          # nur Elite
    press(w, "down", "enter")                  # nur HTTPS
    press(w, "3")                              # unter 1 s (Zahl wählt direkt)
    press(w, "4")                              # 50 Stück
    press(w, "enter")                          # gründlich
    assert isinstance(w.step, SummaryStep)
    press(w, "enter")
    opts = w.result
    assert opts.types == ["http", "socks5"]
    assert opts.filters == Filters(countries={"DE", "AT"}, https_only=True, min_anonymity="elite", max_latency=1000)
    assert opts.want == 50 and not opts.fast


def test_protocols_need_at_least_one():
    w = Wizard(RunOptions())
    press(w, preset_index(w, "Eigene"), "a")   # a = alle abwählen
    step = w.step
    press(w, "enter")
    assert w.step is step and "mindestens" in step.message
    press(w, "space", "enter")
    assert w.step is not step


def test_back_keeps_previous_choices():
    w = Wizard(RunOptions())
    press(w, preset_index(w, "Eigene"), "down", "space", "enter")  # SOCKS4 weg
    press(w, "esc")                                               # zurück zu den Protokollen
    assert isinstance(w.step, MultiStep)
    assert {w.step.options[i].value for i in w.step.checked} == {"http", "socks5"}


def test_adjust_from_summary_prefills_steps():
    w = Wizard(RunOptions())
    press(w, preset_index(w, "Maximal anonym"), "down", "enter")  # Übersicht -> "Anpassen …"
    assert {w.step.options[i].value for i in w.step.checked} == {"socks5"}


def test_presets_keep_filters_from_command_line():
    w = Wizard(RunOptions(filters=Filters(countries={"DE"})))
    press(w, preset_index(w, "Surfen"), "enter")
    assert w.result.filters.countries == {"DE"}   # nicht still verworfen
    assert w.result.filters.https_only            # Voreinstellung wirkt trotzdem


def test_last_preset_hidden_when_identical_to_default():
    labels = [o.label for o in Wizard(RunOptions(), last=RunOptions()).start.options]
    assert "Wie letztes Mal" not in labels


def test_last_preset_and_recheck_only_when_available():
    labels = [o.label for o in Wizard(RunOptions()).start.options]
    assert "Wie letztes Mal" not in labels and "Letzte Treffer neu prüfen" not in labels
    last = RunOptions(types=["socks5"], want=10)
    w = Wizard(RunOptions(), last=last, can_recheck=True)
    press(w, preset_index(w, "Wie letztes Mal"), "enter")
    assert w.result == last
    w = Wizard(RunOptions(), can_recheck=True)
    press(w, preset_index(w, "Letzte Treffer"), "enter")
    assert w.result.recheck == ""


@pytest.mark.parametrize("key", ["q", "ctrl-c"])
def test_quit(key):
    w = press(Wizard(RunOptions()), key)
    assert w.cancelled and w.result is None


def test_cancel_from_summary():
    w = press(Wizard(RunOptions()), "enter", "3")
    assert w.cancelled


@pytest.mark.parametrize("width", [60, 80, 120])
def test_every_screen_renders(width):
    console = Console(width=width, record=True, file=io.StringIO(), color_system=None)
    w = Wizard(RunOptions())
    console.print(w)
    press(w, preset_index(w, "Eigene"))
    for _ in range(len(w.custom)):
        console.print(w)
        press(w, "space" if isinstance(w.step, MultiStep) and not w.step.checked else "down", "enter")
    console.print(w)
    assert "Alles bereit?" in console.export_text()


@pytest.mark.parametrize("raw, name", [
    ("\x1b[A", "up"), ("\x1b[B", "down"), ("\x1bOC", "right"), ("\x1b", "esc"),
    ("\r", "enter"), (" ", "space"), ("\x7f", "backspace"), ("x", "x"),
])
def test_decode_keys(raw, name):
    assert decode(raw) == name


@pytest.mark.parametrize("argv, tty, expected", [
    ([], True, True),        # ohne Argumente im Terminal -> Assistent
    ([], False, False),      # Pipe/Cron -> nie fragen
    (["-y"], True, False),
    (["--want", "5"], True, False),
    (["-i", "--want", "5"], True, True),
])
def test_wants_wizard(monkeypatch, argv, tty, expected):
    monkeypatch.setattr("proxyscraper.cli.is_interactive", lambda: tty)
    assert wants_wizard(parse_args(argv), argv) == expected


def test_short_description_is_readable():
    from proxyscraper.ui.wizard import short_description

    opts = RunOptions(types=["socks5"], want=50, filters=Filters(countries={"DE", "AT"}, https_only=True))
    assert short_description(opts) == "socks5 · AT,DE · nur HTTPS · 50 Stück"
    assert short_description(RunOptions()) == "alle Protokolle"
