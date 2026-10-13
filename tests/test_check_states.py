"""Every check ends as passed, failed, unavailable or skipped – against the lab on localhost (tests/lab.py).

The contract: a check that didn't run is never "passed", and a check target that is down never turns the
proxies checked against it into failures.
"""

import asyncio
import contextlib
import csv
import json

import pytest

from proxyscraper import checker as ck
from proxyscraper import output, pipeline
from proxyscraper.checkstate import (
    BASIC,
    CONFIRM,
    CONTENT,
    FAILED,
    HTTPS,
    PASSED,
    REASONS,
    SKIPPED,
    UNAVAILABLE,
    Check,
    legacy_bool,
    reason_for,
)
from proxyscraper.geo import GeoResolver
from proxyscraper.options import Filters, RunOptions
from proxyscraper.ui import CheckDashboard, LiveStats
from tests.lab import INJECTED, OWN_IP, PAGE, Lab

EXIT = "203.0.113.20"


def in_lab(scenario, **checker_options):
    """Run `scenario(lab, checker)` inside a fresh lab."""
    async def go():
        async with Lab() as lab:
            return await scenario(lab, await lab.checker(**checker_options))
    return asyncio.run(go())


async def all_checks(c: ck.Checker, proxy: str):
    """The checks in the order a run does them; stops where a run would stop."""
    result, basic = await c.check_detailed(f"http {proxy}")
    if result is None:
        return None, {BASIC: basic}
    if await c.confirm(result) and not await c.tampers(result):
        await c.enrich(result)
    return result, result.checks


def states(checks) -> dict:
    return {name: (check.state, check.reason) for name, check in checks.items()}


# --------------------------------------------------------------------------- the eight cases

def test_a_good_proxy_passes_everything_with_time_target_and_measurements():
    async def scenario(lab, c):
        return await all_checks(c, await lab.proxy(EXIT)), lab

    (result, checks), lab = in_lab(scenario)
    assert states(checks) == {BASIC: (PASSED, ""), CONFIRM: (PASSED, ""), CONTENT: (PASSED, ""), HTTPS: (PASSED, "")}
    assert result.exit_ip == EXIT and result.https is True and result.anonymity == "elite"
    assert checks[BASIC].target == f"localhost:{lab.judge_port}" and checks[BASIC].data == {"exit_ip": EXIT}
    assert checks[CONFIRM].target == f"localhost:{lab.confirm_port}"
    assert checks[CONTENT].data == {"bytes": len(PAGE)}
    assert checks[HTTPS].target == f"localhost:{lab.tls_port}"
    assert "nothing about other sites" in checks[HTTPS].limits  # passed TLS is not a security certificate
    assert result.checked_at == checks[BASIC].at
    for check in checks.values():
        assert check.at.endswith("+00:00") and isinstance(check.ms, int)


def test_a_proxy_that_answers_too_late_is_a_timeout_not_a_verdict():
    async def scenario(lab, c):
        return await all_checks(c, await lab.proxy(EXIT, answers_after=1.0))

    result, checks = in_lab(scenario, timeout=0.3)
    assert result is None and states(checks) == {BASIC: (FAILED, "timeout")}


def test_a_closed_port_is_connect_refused():
    async def scenario(lab, c):
        return await all_checks(c, await lab.closed_port()), c

    (result, checks), c = in_lab(scenario)
    assert result is None and checks[BASIC].reason in ("connect_refused", "connect_timeout")  # Windows waits
    assert sum(c.failures.values()) == 1


def test_a_page_instead_of_an_ip_is_an_invalid_response():
    async def scenario(lab, c):
        return await all_checks(c, await lab.proxy(EXIT, garbage=True))

    result, checks = in_lab(scenario)
    assert result is None and states(checks) == {BASIC: (FAILED, "invalid_response")}


def test_an_unreachable_confirm_target_is_unavailable_not_failed():
    """The target stops answering during the run: the proxy is kept and says so."""
    async def scenario(lab, c):
        proxy = await lab.proxy(EXIT)
        lab.confirm_down = True
        return await all_checks(c, proxy)

    result, checks = in_lab(scenario)
    assert (checks[CONFIRM].state, checks[CONFIRM].reason) == (UNAVAILABLE, "target_unreachable")
    assert checks[CONTENT].state == UNAVAILABLE  # no page came back, so nothing was compared
    assert result.anonymity == ""                # and nothing is claimed about anonymity
    assert checks[HTTPS].state == PASSED         # the other target is fine


def test_without_a_control_a_failed_second_request_stays_failed():
    async def scenario(lab, c):
        proxy = await lab.proxy(EXIT)
        lab.confirm_down = True
        return await all_checks(c, proxy)

    _, checks = in_lab(scenario, controls=False)
    assert checks[CONFIRM].state == FAILED and CONTENT not in checks


def test_no_confirm_target_at_start_never_reads_as_passed():
    async def scenario(lab, c):
        return await all_checks(c, await lab.proxy(EXIT, only_first_target=True))

    result, checks = in_lab(scenario, confirm=False)
    assert result is not None  # kept, as before – but nothing says it was confirmed
    assert states(checks)[CONFIRM] == (UNAVAILABLE, "target_not_configured")
    assert states(checks)[CONTENT] == (UNAVAILABLE, "target_not_configured")
    assert "no second request ran" in checks[CONFIRM].limits


def test_a_missing_reference_is_unavailable():
    async def scenario(lab, c):
        return await all_checks(c, await lab.proxy(EXIT, rewrite=lambda body: INJECTED))

    result, checks = in_lab(scenario, reference=False)
    assert states(checks)[CONTENT] == (UNAVAILABLE, "no_reference") and checks[CONFIRM].state == PASSED
    assert result is not None


def test_changed_content_fails_with_what_was_measured_and_no_verdict():
    async def scenario(lab, c):
        return await all_checks(c, await lab.proxy(EXIT, rewrite=lambda body: INJECTED))

    _, checks = in_lab(scenario)
    content = checks[CONTENT]
    assert (content.state, content.reason) == (FAILED, "content_mismatch")
    assert content.data["bytes"] == len(INJECTED) and content.data["script_tags"] == 1
    assert len(content.data["sha256"]) == 16
    assert "doesn't tell which" in content.limits
    assert HTTPS not in checks  # a run drops it here


def test_a_page_that_changed_at_its_source_is_not_blamed_on_the_proxy():
    async def scenario(lab, c):
        proxy = await lab.proxy(EXIT)
        lab.page = PAGE + b"<!-- edited -->"  # after the reference was taken
        return await all_checks(c, proxy)

    _, checks = in_lab(scenario)
    assert checks[CONTENT].state == PASSED


def test_a_certificate_that_does_not_verify_is_a_tls_failure():
    async def scenario(lab, c):
        return await all_checks(c, await lab.proxy(EXIT, breaks_tls=True))

    result, checks = in_lab(scenario)
    assert states(checks)[HTTPS] == (FAILED, "tls_certificate_invalid") and result.https is False
    assert checks[CONFIRM].state == PASSED  # plain HTTP through it works


def test_a_refused_tunnel_is_a_failure_while_the_target_answers():
    async def scenario(lab, c):
        return await all_checks(c, await lab.proxy(EXIT, no_connect=True))

    result, checks = in_lab(scenario)
    assert states(checks)[HTTPS] == (FAILED, "tunnel_refused") and result.https is False


def test_an_https_target_that_is_down_is_unavailable_and_https_stays_unknown():
    async def scenario(lab, c):
        proxy = await lab.proxy(EXIT)
        await lab.stop_https()
        return await all_checks(c, proxy)

    result, checks = in_lab(scenario)
    assert states(checks)[HTTPS] == (UNAVAILABLE, "target_unreachable")
    assert result.https is None  # not False: nothing was measured


def test_fast_mode_skips_https_and_says_so():
    async def scenario(lab, c):
        return await all_checks(c, await lab.proxy(EXIT))

    result, checks = in_lab(scenario, https_test=False)
    assert states(checks)[HTTPS] == (SKIPPED, "fast_mode") and result.https is None


# --------------------------------------------------------------------------- what a failed check may claim

def test_another_exit_ip_on_the_second_site_is_a_mismatch_not_a_honeypot():
    async def scenario(lab, c):
        return await all_checks(c, await lab.proxy(EXIT, second_exit_ip="203.0.113.21"))

    _, checks = in_lab(scenario)
    confirm = checks[CONFIRM]
    assert (confirm.state, confirm.reason) == (FAILED, "exit_ip_mismatch")
    assert confirm.data == {"exit_ip": EXIT, "second_exit_ip": "203.0.113.21"}
    assert "can't tell which" in confirm.limits


def test_a_proxy_that_only_answers_the_first_check_fails_the_second():
    async def scenario(lab, c):
        return await all_checks(c, await lab.proxy(EXIT, only_first_target=True))

    _, checks = in_lab(scenario)
    assert states(checks)[CONFIRM] == (FAILED, "bad_status")


def test_a_proxy_that_passes_our_ip_on_is_transparent():
    async def scenario(lab, c):
        return await all_checks(c, await lab.proxy(EXIT, adds_header=f"X-Forwarded-For: {OWN_IP}"))

    result, checks = in_lab(scenario)
    assert checks[CONFIRM].state == PASSED and result.anonymity == "transparent"


def test_the_control_asks_the_target_once_however_many_proxies_fail():
    asked = []

    async def scenario(lab, c):
        probe = c.controls[CONFIRM]

        async def counting():
            asked.append(1)
            return await probe()

        c.controls[CONFIRM] = counting
        proxies = [await lab.proxy(f"203.0.113.{30 + i}") for i in range(12)]
        lab.confirm_down = True
        return await asyncio.gather(*(all_checks(c, p) for p in proxies))

    outcomes = in_lab(scenario)
    assert {checks[CONFIRM].reason for _, checks in outcomes} == {"target_unreachable"}
    assert len(asked) == 1


def test_running_out_of_sockets_says_nothing_about_the_proxy():
    assert reason_for(OSError(24, "Too many open files")) == "local_resource_limit"
    assert reason_for(asyncio.TimeoutError()) == "timeout"
    assert reason_for(ConnectionResetError()) == "connection_closed"


def test_every_reason_code_is_explained():
    async def scenario(lab, c):
        seen = set()
        for options in ({}, {"garbage": True}, {"no_connect": True}, {"breaks_tls": True},
                        {"second_exit_ip": "203.0.113.9"}, {"rewrite": lambda b: b""}, {"only_first_target": True}):
            _, checks = await all_checks(c, await lab.proxy(EXIT, **options))
            seen |= {check.reason for check in checks.values() if check.reason}
        return seen

    assert in_lab(scenario) <= set(REASONS)


# --------------------------------------------------------------------------- a whole run

def lab_run(tmp_path, prepare, opts=None, **checker_options):
    async def go():
        async with Lab() as lab:
            c = await lab.checker(**checker_options)
            jobs = [f"http {p}" for p in await prepare(lab)]
            stats = LiveStats({"http": len(jobs)})
            writer = output.ResultWriter(run_dir=tmp_path / "run")
            options = opts or RunOptions(no_geo=True)
            dashboard = CheckDashboard(stats, writer.live_path, 4, options.details)
            run = await pipeline.run_checks(jobs, c, options, dashboard, writer, GeoResolver(enabled=False),
                                            live_factory=lambda _: contextlib.nullcontext())
            writer.finalize(run.results)
            return run, stats, jobs
    return asyncio.run(go())


def test_a_confirm_outage_does_not_fail_every_proxy_of_the_run(tmp_path):
    async def prepare(lab):
        proxies = [await lab.proxy(f"203.0.113.{40 + i}") for i in range(5)]
        lab.confirm_down = True
        return proxies

    run, stats, jobs = lab_run(tmp_path, prepare)
    assert run.working == set(jobs) and stats.fakes == 0  # before: all five counted as fake and learned as dead
    assert stats.confirm_unavailable == 5
    assert run.states[CONFIRM] == {"unavailable:target_unreachable": 5}
    rows = json.loads((tmp_path / "run" / "proxies.json").read_text())
    assert {row["checks"]["confirm"]["state"] for row in rows} == {UNAVAILABLE}
    assert all(row["anonymity"] == "" and row["checked_at"] for row in rows)


def test_a_run_counts_each_state_and_keeps_the_old_json_fields(tmp_path):
    async def prepare(lab):
        return [await lab.proxy("203.0.113.50"), await lab.proxy("203.0.113.51", no_connect=True),
                await lab.proxy("203.0.113.52", second_exit_ip="203.0.113.53"),
                await lab.proxy("203.0.113.54", rewrite=lambda b: INJECTED), await lab.closed_port()]

    run, stats, _ = lab_run(tmp_path, prepare)
    assert len(run.working) == 2 and (stats.fakes, stats.tampered) == (1, 1)
    assert run.states[CONFIRM] == {"passed": 3, "failed:exit_ip_mismatch": 1}
    assert run.states[CONTENT] == {"passed": 2, "failed:content_mismatch": 1}
    assert run.states[HTTPS] == {"passed": 1, "failed:tunnel_refused": 1}
    rows = {row["exit_ip"]: row for row in json.loads((tmp_path / "run" / "proxies.json").read_text())}
    good = rows["203.0.113.50"]
    # everything a consumer of 1.28 reads is still there, with the same types
    for name in ("ptype", "proxy", "latency", "exit_ip", "https", "anonymity", "country", "targets", "asn", "org",
                 "hosting", "blocklisted", "speed_kbps", "url"):
        assert name in good
    assert good["https"] is True and rows["203.0.113.51"]["https"] is False
    assert set(good["checks"]) == {BASIC, CONFIRM, CONTENT, HTTPS}
    assert good["checks"]["https"]["state"] == PASSED and "reason" not in good["checks"]["https"]
    with (tmp_path / "run" / "proxies.csv").open(newline="", encoding="utf-8") as fh:
        table = list(csv.DictReader(fh))
    assert {row["check_https"] for row in table} == {"passed", "failed:tunnel_refused"}
    assert all(row["check_confirm"] == "passed" for row in table)


def test_https_skipped_by_a_filter_is_marked_skipped(tmp_path):
    async def prepare(lab):
        return [await lab.proxy("203.0.113.60", adds_header="Via: 1.1 lab")]  # anonymous, not elite

    opts = RunOptions(no_geo=True, filters=Filters(https_only=True, min_anonymity="elite"))
    run, stats, _ = lab_run(tmp_path, prepare, opts)
    result = run.results[0]
    assert result.anonymity == "anonymous" and stats.details_saved == 1
    assert result.checks[HTTPS].label() == "skipped:filtered_out" and result.https is None


def test_old_fields_read_null_for_anything_not_measured():
    assert legacy_bool(Check(PASSED)) is True and legacy_bool(Check(FAILED, "tunnel_refused")) is False
    assert legacy_bool(Check(UNAVAILABLE, "target_unreachable")) is None
    assert legacy_bool(Check(SKIPPED, "fast_mode")) is None and legacy_bool(None) is None


@pytest.mark.parametrize("raw", [None, [], "passed", {"state": "great"}, {"reason": "x"}])
def test_checks_from_a_published_list_are_read_defensively(raw):
    assert Check.from_dict(raw) is None


def test_a_check_round_trips_through_json():
    check = Check(FAILED, "content_mismatch", "httpbin.org:80/html", "2026-10-13T12:00:00+00:00", 412,
                  {"bytes": 10}, "limits")
    assert Check.from_dict(json.loads(json.dumps(check.as_dict()))) == check
    assert Check(PASSED).as_dict() == {"state": "passed"}
