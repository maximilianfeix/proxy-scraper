"""proxy-scraper --pick: proxies from the hourly list on stdout, with the usual filters, no scan."""

import pytest

from proxyscraper import api, cli
from tests.test_live_api import ROWS, STATS, fetch_from


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    rows = [dict(ROWS[0], sites={"google": True}), ROWS[1], ROWS[2]]
    monkeypatch.setattr(api, "_live_fetch", fetch_from({"proxies.json": rows, "stats.json": STATS}))


def test_one_proxy_by_default_and_nothing_else_on_stdout(capsys):
    assert cli.run(["--pick"]) == 0
    assert capsys.readouterr().out == "http://2.2.2.2:80\n"  # the fastest


def test_the_usual_filters_apply(capsys):
    assert cli.run(["--pick", "5", "--types", "socks4", "socks5", "--country", "DE", "--https-only"]) == 0
    assert capsys.readouterr().out.splitlines() == ["socks4://3.3.3.3:4145", "socks5://1.1.1.1:1080"]
    assert cli.run(["--pick", "--min-uptime", "90", "--works-on", "google"]) == 0
    assert capsys.readouterr().out == "socks5://1.1.1.1:1080\n"


def test_nothing_matching_is_exit_1_with_a_hint_on_stderr(capsys):
    assert cli.run(["--pick", "--country", "JP"]) == 1
    out = capsys.readouterr()
    assert out.out == "" and "no proxy" in out.err.lower()


def test_pick_only_filters_need_pick(capsys):
    with pytest.raises(SystemExit):
        cli.run(["--min-uptime", "90"])
    assert "--pick" in capsys.readouterr().err


@pytest.mark.parametrize("extra", [["--target", "discord.com"], ["--serve"], ["--recheck"], ["--want", "5"],
                                   ["-o", "x.txt"], ["--export", "clash"]])
def test_options_for_a_scan_are_an_error_not_ignored(extra, capsys):
    with pytest.raises(SystemExit):
        cli.run(["--pick", *extra])
    assert "--pick" in capsys.readouterr().err


def test_min_speed_keeps_only_proxies_that_downloaded_that_fast(monkeypatch, capsys):
    rows = [dict(ROWS[0], speed_kbps=300), dict(ROWS[2], speed_kbps=40), ROWS[1]]
    monkeypatch.setattr(api, "_live_fetch", fetch_from({"proxies.json": rows, "stats.json": STATS}))
    assert cli.run(["--pick", "5", "--min-speed", "100"]) == 0
    assert capsys.readouterr().out == "socks5://1.1.1.1:1080\n"
