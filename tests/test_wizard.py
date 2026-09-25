"""The setup wizard as key sequences – without a real terminal."""

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
    w = press(Wizard(RunOptions()), "enter", "enter")  # "Find everything" -> summary -> start
    assert w.result == RunOptions()


def test_web_preset():
    w = Wizard(RunOptions())
    press(w, preset_index(w, "Browsing"), "enter")
    assert w.result.types == ["http", "socks5"]
    assert w.result.filters == Filters(https_only=True, min_anonymity="anonymous", max_latency=3000)


def test_presets_keep_technical_options_from_command_line():
    w = Wizard(RunOptions(concurrency=500, timeout=5.0))
    press(w, preset_index(w, "Maximum anonymity"), "enter")
    assert (w.result.concurrency, w.result.timeout, w.result.types) == (500, 5.0, ["socks5"])


def test_custom_walkthrough():
    w = Wizard(RunOptions())
    press(w, preset_index(w, "Custom"))
    # protocols: deselect SOCKS4 (the cursor is on HTTP)
    press(w, "down", "space", "enter")
    # countries: tick DE by jumping to the letter, AT right below it
    press(w, "g", "space", "down", "space", "enter")  # "a" is select all, so Austria by arrow key
    press(w, "down", "down", "enter")          # elite only
    press(w, "down", "enter")                  # HTTPS only
    press(w, "2")                              # target site Google
    press(w, "3")                              # under 1 s (a number picks directly)
    press(w, "4")                              # 50 proxies
    press(w, "enter")                          # no proxy server
    press(w, "enter")                          # thorough
    assert isinstance(w.step, SummaryStep)
    press(w, "enter")
    opts = w.result
    assert opts.types == ["http", "socks5"]
    assert opts.filters == Filters(countries={"DE", "AT"}, https_only=True, min_anonymity="elite", max_latency=1000,
                                   targets=["https://www.google.com/"])
    assert opts.want == 50 and not opts.fast


def test_protocols_need_at_least_one():
    w = Wizard(RunOptions())
    press(w, preset_index(w, "Custom"), "a")   # a = deselect all
    step = w.step
    press(w, "enter")
    assert w.step is step and "at least" in step.message
    press(w, "space", "enter")
    assert w.step is not step


def test_back_keeps_previous_choices():
    w = Wizard(RunOptions())
    press(w, preset_index(w, "Custom"), "down", "space", "enter")  # SOCKS4 off
    press(w, "esc")                                               # back to the protocols
    assert isinstance(w.step, MultiStep)
    assert {w.step.options[i].value for i in w.step.checked} == {"http", "socks5"}


def test_adjust_from_summary_prefills_steps():
    w = Wizard(RunOptions())
    press(w, preset_index(w, "Maximum anonymity"), "down", "enter")  # summary -> "Adjust …"
    assert {w.step.options[i].value for i in w.step.checked} == {"socks5"}


def test_presets_keep_filters_from_command_line():
    w = Wizard(RunOptions(filters=Filters(countries={"DE"})))
    press(w, preset_index(w, "Browsing"), "enter")
    assert w.result.filters.countries == {"DE"}   # not silently dropped
    assert w.result.filters.https_only            # the preset still applies


def test_last_preset_hidden_when_identical_to_default():
    labels = [o.label for o in Wizard(RunOptions(), last=RunOptions()).start.options]
    assert "Same as last time" not in labels


def test_last_preset_and_recheck_only_when_available():
    labels = [o.label for o in Wizard(RunOptions()).start.options]
    assert "Same as last time" not in labels and "Recheck the last hits" not in labels
    last = RunOptions(types=["socks5"], want=10)
    w = Wizard(RunOptions(), last=last, can_recheck=True)
    press(w, preset_index(w, "Same as last time"), "enter")
    assert w.result == last
    w = Wizard(RunOptions(), can_recheck=True)
    press(w, preset_index(w, "Recheck the last"), "enter")
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
    press(w, preset_index(w, "Custom"))
    for _ in range(len(w.custom)):
        console.print(w)
        press(w, "space" if isinstance(w.step, MultiStep) and not w.step.checked else "down", "enter")
    console.print(w)
    assert "All set?" in console.export_text()


@pytest.mark.parametrize("raw, name", [
    ("\x1b[A", "up"), ("\x1b[B", "down"), ("\x1bOC", "right"), ("\x1b", "esc"),
    ("\r", "enter"), (" ", "space"), ("\x7f", "backspace"), ("x", "x"),
])
def test_decode_keys(raw, name):
    assert decode(raw) == name


@pytest.mark.parametrize("argv, tty, expected", [
    ([], True, True),        # no arguments in a terminal -> wizard
    ([], False, False),      # pipe/cron -> never ask
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
    assert short_description(opts) == "socks5 · AT,DE · HTTPS only · 50 proxies"
    assert short_description(RunOptions()) == "all protocols"


def test_target_step_keeps_custom_targets_from_command_line():
    from proxyscraper.ui.wizard import TargetStep

    w = Wizard(RunOptions(filters=Filters(targets=["https://example.org/login"])))
    press(w, preset_index(w, "Custom"))
    while not isinstance(w.step, TargetStep):
        press(w, "enter")
    assert w.step.options[w.step.cursor].label == "As given"   # preselected instead of overwritten
    press(w, "enter")
    assert w.opts.filters.targets == ["https://example.org/login"]


def test_quick_server_preset():
    w = Wizard(RunOptions(), can_recheck=True)
    press(w, preset_index(w, "Proxy server right away"), "enter")
    assert (w.result.recheck, w.result.serve) == ("", 8899)
    assert "Proxy server right away" not in [o.label for o in Wizard(RunOptions()).start.options]


def test_serve_step_keeps_custom_port_from_command_line():
    from proxyscraper.ui.wizard import ServeStep

    w = Wizard(RunOptions(serve=9000))
    press(w, preset_index(w, "Custom"))
    while not isinstance(w.step, ServeStep):
        press(w, "enter")
    assert w.step.options[w.step.cursor].value == 9000   # preselected instead of silently "No"
    press(w, "enter")
    assert w.opts.serve == 9000
