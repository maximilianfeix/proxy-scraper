"""--pick --verify and --diagnose against the lab on localhost: what goes to stdout, what to stderr, the exit
codes, the limits on how much is tried, and that a password never shows up."""

import asyncio
import json
from datetime import datetime, timedelta, timezone

import pytest

from proxyscraper import api, cli, verify
from proxyscraper.checkstate import BASIC, CONFIRM, CONTENT, HTTPS
from tests.lab import INJECTED, Lab, LabThread
from tests.test_live_api import fetch_from


def stats(minutes_old: int = 10) -> dict:
    updated = datetime.now(timezone.utc) - timedelta(minutes=minutes_old)
    return {"updated": updated.isoformat(timespec="seconds"), "run_hours": 1}


def row(proxy: str, latency: int = 100, **extra) -> dict:
    return {"url": f"http://{proxy}", "proxy": proxy, "ptype": "http", "latency": latency, "exit_ip": "203.0.113.9",
            "https": True, "anonymity": "elite", "country": "DE", "streak": 30, "uptime_7d": 95, **extra}


@pytest.fixture
def lab(monkeypatch):
    with LabThread() as running:
        async def prepare(timeout, connect_timeout):
            return await running.lab.checker(timeout=min(timeout, 2.0), **running.options)

        running.options = {}
        monkeypatch.setattr(verify, "prepare", prepare)
        yield running


def publish(monkeypatch, rows, minutes_old: int = 10) -> None:
    monkeypatch.setattr(api, "_live_fetch", fetch_from({"proxies.json": rows, "stats.json": stats(minutes_old)}))


# --------------------------------------------------------------------------- --pick --verify

def test_verify_prints_only_proxies_that_pass_now_and_explains_the_rest_on_stderr(lab, monkeypatch, capsys):
    dead = lab.run(lab.closed_port())
    changed = lab.run(lab.proxy("203.0.113.11", rewrite=lambda body: INJECTED))
    good = lab.run(lab.proxy("203.0.113.12"))
    publish(monkeypatch, [row(dead, 50), row(changed, 60), row(good, 70)])  # best first: the good one is last
    assert cli.run(["--pick", "--verify"]) == 0
    out = capsys.readouterr()
    assert out.out == f"http://{good}\n"  # nothing but the URL
    assert "not usable from this machine" in out.err and "failed the content check" in out.err


def test_plain_pick_is_unchanged_and_checks_nothing(lab, monkeypatch, capsys):
    dead = lab.run(lab.closed_port())
    publish(monkeypatch, [row(dead)])
    assert cli.run(["--pick"]) == 0
    out = capsys.readouterr()
    assert out.out == f"http://{dead}\n" and out.err == ""


def test_fewer_than_asked_for_is_exit_3_with_the_ones_that_passed(lab, monkeypatch, capsys):
    good = lab.run(lab.proxy("203.0.113.13"))
    publish(monkeypatch, [row(good), row(lab.run(lab.closed_port()))])
    assert cli.run(["--pick", "2", "--verify"]) == verify.EXIT_PARTIAL
    out = capsys.readouterr()
    assert out.out == f"http://{good}\n"
    assert "only 1 of 2 passed" in out.err and "all 2 matching proxies of the list were tried" in out.err


def test_none_passing_is_exit_1_and_an_empty_stdout(lab, monkeypatch, capsys):
    publish(monkeypatch, [row(lab.run(lab.closed_port()))])
    assert cli.run(["--pick", "--verify"]) == 1
    out = capsys.readouterr()
    assert out.out == "" and "only 0 of 1" in out.err


def test_https_only_also_requires_the_https_test(lab, monkeypatch, capsys):
    no_tunnel = lab.run(lab.proxy("203.0.113.14", no_connect=True))
    good = lab.run(lab.proxy("203.0.113.15"))
    publish(monkeypatch, [row(no_tunnel), row(good)])
    assert cli.run(["--pick", "--verify", "--https-only"]) == 0
    assert capsys.readouterr().out == f"http://{good}\n"


def test_without_a_confirm_target_nothing_counts_as_verified(lab, monkeypatch, capsys):
    lab.options = {"confirm": False}
    publish(monkeypatch, [row(lab.run(lab.proxy("203.0.113.16")))])
    assert cli.run(["--pick", "--verify"]) == 1
    out = capsys.readouterr()
    assert out.out == "" and "nothing can be verified right now" in out.err


def test_json_keeps_list_time_and_check_time_apart(lab, monkeypatch, capsys):
    good = lab.run(lab.proxy("203.0.113.17"))
    publish(monkeypatch, [row(good)], minutes_old=20)
    assert cli.run(["--pick", "--verify", "--json"]) == 0
    out = capsys.readouterr()
    data = json.loads(out.out)  # stdout is exactly one JSON document
    assert data["list"]["age_minutes"] == 20 and data["list"]["stale"] is False and data["verified"] is True
    proxy = data["proxies"][0]
    assert proxy["url"] == f"http://{good}" and proxy["exit_ip"] == "203.0.113.17"
    assert proxy["checked_at"] > data["list"]["updated"]  # checked now, listed 20 minutes ago
    assert {name: check["state"] for name, check in proxy["checks"].items()} == dict.fromkeys(
        (BASIC, CONFIRM, CONTENT, HTTPS), "passed")
    assert (data["wanted"], data["tried"], data["budget_exhausted"]) == (1, 1, False)


def test_pick_json_without_verify_says_nothing_was_checked_now(monkeypatch, capsys):
    listed = row("1.1.1.1:80", checked_at="2026-10-13T10:17:05+00:00",
                 checks={"confirm": {"state": "passed", "at": "2026-10-13T10:17:06+00:00"}, "https": "broken"})
    publish(monkeypatch, [listed])
    assert cli.run(["--pick", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["verified"] is False
    assert data["proxies"][0]["checked_at"] == "2026-10-13T10:17:05+00:00"
    assert data["proxies"][0]["checks"] == {"confirm": {"state": "passed", "at": "2026-10-13T10:17:06+00:00"}}


def test_an_overdue_list_is_called_stale_on_stderr_and_in_json(monkeypatch, capsys):
    publish(monkeypatch, [row("1.1.1.1:80")], minutes_old=200)
    assert cli.run(["--pick"]) == 0
    out = capsys.readouterr()
    assert out.out == "http://1.1.1.1:80\n"
    assert "200 minutes old" in out.err and "110 minutes overdue" in out.err and "--verify" in out.err
    assert cli.run(["--pick", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["list"]["stale"] is True


def test_verify_needs_pick(capsys):
    with pytest.raises(SystemExit):
        cli.run(["--verify"])
    assert "--pick" in capsys.readouterr().err


# --------------------------------------------------------------------------- limits

def test_attempts_are_bounded():
    assert verify.attempts_for(1, 5000) == verify.MIN_ATTEMPTS
    assert verify.attempts_for(4, 5000) == 20
    assert verify.attempts_for(100, 5000) == verify.MAX_ATTEMPTS
    assert verify.attempts_for(3, 2) == 2


def test_no_more_candidates_are_tried_than_allowed_and_never_too_many_at_once():
    async def go():
        async with Lab() as lab:
            checker = await lab.checker(timeout=1.0)
            running = peak = 0
            examined = []
            inner = checker.check_detailed

            async def counting(key):
                nonlocal running, peak
                running += 1
                peak = max(peak, running)
                examined.append(key)
                try:
                    return await inner(key)
                finally:
                    running -= 1

            checker.check_detailed = counting
            dead = [f"http {await lab.closed_port()}" for _ in range(40)]
            selection = await verify.pick_verified(checker, dead, want=3)
            return selection, len(examined), peak

    selection, examined, peak = asyncio.run(go())
    assert examined == selection.tried == selection.attempts == 15  # 3 wanted x 5, of 40 offered
    assert selection.verified == [] and selection.exhausted and peak <= 6


def test_it_stops_as_soon_as_enough_passed():
    async def go():
        async with Lab() as lab:
            checker = await lab.checker()
            keys = [f"http {await lab.proxy(f'203.0.113.{100 + i}')}" for i in range(12)]
            return await verify.pick_verified(checker, keys, want=1), keys

    selection, keys = asyncio.run(go())
    assert [r.key for r in selection.verified] == keys[:1]  # list order: the best one, not the quickest
    assert selection.tried <= 4 and not selection.exhausted


def test_the_time_limit_ends_it_and_says_so():
    async def go():
        async with Lab() as lab:
            checker = await lab.checker(timeout=5.0)
            slow = [f"http {await lab.proxy('203.0.113.120', answers_after=3.0)}" for _ in range(4)]
            selection = await verify.pick_verified(checker, slow, want=1, budget=0.3)
            return selection, verify.shortfall_message(selection, 1, False, checker)

    selection, message = asyncio.run(go())
    assert selection.out_of_time and selection.verified == [] and "time limit" in message


def test_cancelling_stops_every_check_still_running():
    async def go():
        async with Lab() as lab:
            checker = await lab.checker(timeout=5.0)
            slow = [f"http {await lab.proxy('203.0.113.121', answers_after=4.0)}" for _ in range(6)]
            def checking():  # tasks of the checks themselves – the lab's own handlers run on this loop too
                return [t for t in asyncio.all_tasks()
                        if any(part in t.get_coro().__qualname__ for part in ("pick_verified", "Checker", "examine"))]

            task = asyncio.ensure_future(verify.pick_verified(checker, slow, want=2))
            await asyncio.sleep(0.2)
            during = len(checking())
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            await asyncio.sleep(0.05)
            return during, len(checking())

    during, after = asyncio.run(go())
    assert during >= 4 and after == 0  # nothing keeps connecting in the background


# --------------------------------------------------------------------------- --diagnose

def test_diagnosis_shows_every_check_with_what_it_found(lab, capsys):
    good = lab.run(lab.proxy("203.0.113.30"))
    assert cli.run(["--diagnose", f"http://{good}"]) == 0
    out = capsys.readouterr().out
    assert f"Proxy      http://{good}" in out and "from this machine" in out
    for expected in ("✔ Reach", "exit IP 203.0.113.30", "✔ Second request", "anonymity: elite", "✔ Content",
                     "arrived unchanged", "✔ HTTPS", "Result     passed every check",
                     "nothing about other sites", "not a promise for later"):
        assert expected in out


def test_diagnosis_names_the_failed_check_and_is_exit_1(lab, capsys):
    no_tunnel = lab.run(lab.proxy("203.0.113.31", no_connect=True))
    assert cli.run(["--diagnose", no_tunnel]) == 1  # a bare host:port is read as HTTP
    out = capsys.readouterr().out
    assert "✘ HTTPS" in out and "tunnel_refused: the proxy did not open a tunnel to port 443" in out
    assert "works for plain HTTP; HTTPS through it did not work" in out


def test_diagnosis_of_a_dead_proxy_marks_the_rest_as_not_run(lab, capsys):
    assert cli.run(["--diagnose", f"http://{lab.run(lab.closed_port())}", "--json"]) == 1
    data = json.loads(capsys.readouterr().out)
    assert data["verdict"] == "not usable from this machine right now" and data["exit_ip"] is None
    assert data["checks"]["basic"]["state"] == "failed"
    assert {data["checks"][name]["reason"] for name in (CONFIRM, CONTENT, HTTPS)} == {"earlier_check_failed"}


def test_diagnosis_with_a_check_target_down_is_exit_3_not_a_failure(lab, capsys):
    good = lab.run(lab.proxy("203.0.113.32"))
    lab.lab.confirm_down = True
    assert cli.run(["--diagnose", good, "--json"]) == verify.EXIT_PARTIAL
    data = json.loads(capsys.readouterr().out)
    assert data["checks"]["confirm"] == {**data["checks"]["confirm"], "state": "unavailable",
                                         "reason": "target_unreachable"}
    assert "not verified" in data["verdict"] and data["anonymity"] is None


def test_diagnosis_fast_skips_https(lab, capsys):
    good = lab.run(lab.proxy("203.0.113.33"))
    assert cli.run(["--diagnose", good, "--fast", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["checks"]["https"]["state"] == "skipped" and data["https"] is None
    assert data["verdict"] == "works for plain HTTP; HTTPS was not tested"


@pytest.mark.parametrize("text", ["nonsense", "ftp://1.2.3.4:21", "http://1.2.3.4", "socks5://1.2.3.4:99999",
                                  "http://1.2.3.4:80/path"])
def test_what_is_not_a_proxy_is_exit_2(text, capsys):
    assert cli.run(["--diagnose", text]) == verify.EXIT_USAGE
    out = capsys.readouterr()
    assert out.out == "" and "not a proxy" in out.err


def test_a_password_never_shows_up_in_text_json_or_stderr(lab, capsys):
    good = lab.run(lab.proxy("203.0.113.34"))
    secret = "hunter2-s3cret"
    for extra in ([], ["--json"]):
        assert cli.run(["--diagnose", f"http://alice:{secret}@{good}", *extra]) == 0
        out = capsys.readouterr()
        assert secret not in out.out and secret not in out.err
        assert f"http://alice:***@{good}" in out.out


def test_parse_proxy_keeps_logins_and_takes_private_addresses():
    assert verify.parse_proxy("socks5h://10.0.0.5:1080") == "socks5 10.0.0.5:1080"
    assert verify.parse_proxy(" 127.0.0.1:3128 ") == "http 127.0.0.1:3128"
    assert verify.parse_proxy("http://alice:p%40ss@proxy.example:8080") == "http alice:p%40ss@proxy.example:8080"
    assert verify.shown("http", "alice:p%40ss@proxy.example:8080") == "http://alice:***@proxy.example:8080"


def test_stale_minutes():
    assert verify.stale_minutes(59, 1) is None and verify.stale_minutes(90, 1) is None
    assert verify.stale_minutes(200, 1) == 110 and verify.stale_minutes(None, 1) is None
