"""Every check ends as passed, failed, unavailable or skipped – against the lab on localhost (tests/lab.py).

The contract: a check that didn't run is never "passed", and a check target that is down never turns the
proxies checked against it into failures.
"""

import asyncio
import contextlib
import csv
import dataclasses
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


def test_running_out_of_time_during_the_connect_is_connect_timeout_not_a_silent_proxy(monkeypatch):
    """With connect timeout = timeout the outer limit can fire first; the proxy still never answered."""
    async def scenario(lab, c):
        async def hangs(proxy, detail=False):
            await asyncio.sleep(10)

        monkeypatch.setattr(c, "_connect", hangs)
        c.timeout = 0.2
        return await all_checks(c, await lab.proxy(EXIT))

    result, checks = in_lab(scenario)
    assert result is None and states(checks)[BASIC] == (FAILED, "connect_timeout")


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
    # the columns 1.28 wrote keep their position, the new ones come after them
    assert list(table[0])[:14] == ["ptype", "proxy", "latency", "exit_ip", "https", "anonymity", "country", "targets",
                                   "asn", "org", "hosting", "blocklisted", "speed_kbps", "url"]
    assert list(table[0])[14:] == ["checked_at", "check_basic", "check_confirm", "check_content", "check_https"]
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


# --------------------------------------------------------------------------- what a review found

def test_an_answer_from_before_the_outage_does_not_blame_the_next_proxy():
    """A real failure makes the control ask the target ("fine"). Then the target dies. The proxy checked next
    must not be failed on the strength of that older answer."""
    async def scenario(lab, c):
        picky = await lab.proxy("203.0.113.70", only_first_target=True)
        honest = await lab.proxy("203.0.113.71")
        _, first = await all_checks(c, picky)
        lab.confirm_down = True
        _, second = await all_checks(c, honest)
        return first, second

    first, second = in_lab(scenario)
    assert states(first)[CONFIRM] == (FAILED, "bad_status")  # the target answered directly: the proxy's failure
    assert states(second)[CONFIRM] == (UNAVAILABLE, "target_unreachable")


def test_a_target_with_a_bad_certificate_of_its_own_is_not_the_proxys_tls_failure():
    async def scenario(lab, c):
        c.https_port = lab.untrusted_port  # the HTTPS target itself now serves a certificate nobody trusts
        return await all_checks(c, await lab.proxy(EXIT))

    result, checks = in_lab(scenario)
    assert states(checks)[HTTPS] == (UNAVAILABLE, "target_unreachable") and result.https is None


def test_an_https_target_that_answers_with_an_error_is_not_the_proxys_failure():
    async def scenario(lab, c):
        lab.https_status = b"503 Service Unavailable"
        return await all_checks(c, await lab.proxy(EXIT))

    result, checks = in_lab(scenario)
    assert states(checks)[HTTPS] == (UNAVAILABLE, "target_unreachable") and result.https is None


def test_a_reference_that_changed_since_the_last_look_is_fetched_again():
    async def scenario(lab, c):
        proxy = await lab.proxy(EXIT)
        lab.page = PAGE + b"<!-- one -->"
        _, first = await all_checks(c, proxy)   # the control fetches the page as it is now
        lab.page = PAGE + b"<!-- two -->"       # … and it changes again right after
        _, second = await all_checks(c, proxy)
        return first, second

    first, second = in_lab(scenario)
    assert first[CONTENT].state == PASSED and second[CONTENT].state == PASSED


# short ids: pytest puts the test id into PYTEST_CURRENT_TEST, and Windows refuses variables over 32,767 characters
@pytest.mark.parametrize("body", [b"[" * 200_000, b'{"origin": "9.9.9.9", "headers": ' + b"[" * 200_000],
                         ids=["bare", "inside-headers"])
def test_absurdly_nested_json_from_a_proxy_is_an_unusable_answer_not_a_crash(body):
    assert ck.confirmation_origins(body) is None
    assert ck.classify_anonymity(body, set()) is None


def test_out_of_sockets_is_not_learned_as_a_dead_proxy(tmp_path):
    class Starved:
        def __init__(self):
            self.no_verdict = set()

        async def check(self, key):
            self.no_verdict.add(key)  # what Checker.check does when the basic check is "unavailable"
            return None

    async def go():
        jobs = ["http 1.1.1.1:80", "http 2.2.2.2:80"]
        stats = LiveStats({"http": 2})
        writer = output.ResultWriter(run_dir=tmp_path / "run")
        dashboard = CheckDashboard(stats, writer.live_path, 2, True)
        return await pipeline.run_checks(jobs, Starved(), RunOptions(no_geo=True), dashboard, writer,
                                         GeoResolver(enabled=False), live_factory=lambda _: contextlib.nullcontext())

    run = asyncio.run(go())
    assert run.checked == [] and run.unavailable == 2  # no verdict: nothing for the history or the sources


def test_the_basic_counter_names_the_state_too():
    async def scenario(lab, c):
        await all_checks(c, await lab.closed_port())
        return dict(c.failures)

    failures = in_lab(scenario)
    assert list(failures) in (["failed:connect_refused"], ["failed:connect_timeout"])


def test_the_real_checker_marks_a_check_without_a_verdict(monkeypatch):
    async def scenario(lab, c):
        async def no_sockets(proxy, detail=False):
            raise OSError(24, "Too many open files")

        monkeypatch.setattr(c, "_connect", no_sockets)
        key = f"http {await lab.proxy(EXIT)}"
        return await c.check(key), key, set(c.no_verdict), dict(c.failures)

    result, key, no_verdict, failures = in_lab(scenario)
    assert result is None and no_verdict == {key} and failures == {"unavailable:local_resource_limit": 1}


def test_a_run_uses_check_so_a_replaced_check_is_respected(tmp_path):
    """Code that swaps Checker.check (the proxy server's tests do, callers may) must still be what a run calls."""
    called = []

    async def prepare(lab):
        return [await lab.proxy("203.0.113.90")]

    async def go():
        async with Lab() as lab:
            c = await lab.checker()

            async def replaced(key):
                called.append(key)
                return None

            c.check = replaced
            jobs = [f"http {p}" for p in await prepare(lab)]
            stats = LiveStats({"http": 1})
            writer = output.ResultWriter(run_dir=tmp_path / "run")
            run = await pipeline.run_checks(jobs, c, RunOptions(no_geo=True),
                                            CheckDashboard(stats, writer.live_path, 1, True), writer,
                                            GeoResolver(enabled=False), live_factory=lambda _: contextlib.nullcontext())
            return run, jobs

    run, jobs = asyncio.run(go())
    assert called == jobs and run.checked == jobs


def test_a_dead_first_target_is_not_the_proxys_failure_where_a_control_is_set():
    """--diagnose and --pick --verify have no JudgeWatch: the first request asks its target directly too."""
    async def scenario(lab, c):
        c.controls[BASIC] = lambda: ck.probe_https_target("localhost", "127.0.0.1", 1, c.tls_context, 0.5)  # "down"
        dead_target = await lab.proxy(EXIT, only_first_target=True)  # … and a proxy whose first request fails
        lab.servers[0].close()
        await lab.servers[0].wait_closed()
        return await all_checks(c, dead_target), await all_checks(c, await lab.closed_port())

    (_, through_proxy), (_, no_proxy) = in_lab(scenario)
    assert states(through_proxy)[BASIC] == (UNAVAILABLE, "target_unreachable")
    assert no_proxy[BASIC].state == FAILED  # no connection to the proxy at all: that is the proxy's, target or not


# --------------------------------------------------------------------------- the second target's rate limit

SHARED_EXIT = "203.0.113.80"


def test_proxies_on_one_exit_ip_are_paced_below_the_targets_limit():
    """httpbin.org answers 429 above 17 requests per second per client IP, and free proxies share exit IPs:
    checked all at once, the proxies of one exit tripped that limit themselves."""
    async def scenario(lab, c):
        lab.confirm_rate_limit = 17
        proxies = [await lab.proxy(SHARED_EXIT) for _ in range(12)]  # 24 requests to the second target
        outcomes = await asyncio.gather(*(all_checks(c, p) for p in proxies))
        return [checks for _, checks in outcomes], lab.rate_limited

    all_states, rate_limited = in_lab(scenario, timeout=3.0)
    assert rate_limited == 0  # the pacing kept every exit under the limit, no retry needed
    assert all(states(checks)[CONFIRM] == (PASSED, "") and states(checks)[CONTENT] == (PASSED, "")
               for checks in all_states)


def test_a_429_from_the_target_is_retried_once():
    async def scenario(lab, c):
        proxy = await lab.proxy(EXIT)
        lab.confirm_429 = 1
        return await all_checks(c, proxy)

    result, checks = in_lab(scenario)
    assert states(checks)[CONFIRM] == (PASSED, "") and result.anonymity == "elite"
    assert states(checks)[CONTENT] == (PASSED, "")


def test_a_target_that_keeps_answering_429_says_nothing_about_the_proxy():
    async def scenario(lab, c):
        proxy = await lab.proxy(EXIT)
        lab.confirm_429 = 4  # the first try and the retry, of both the second request and the page
        return await all_checks(c, proxy)

    result, checks = in_lab(scenario)
    assert states(checks)[CONFIRM] == (UNAVAILABLE, "target_rate_limited")
    assert states(checks)[CONTENT] == (UNAVAILABLE, "target_rate_limited")
    assert result.anonymity == ""


def test_a_rate_limited_target_does_not_fail_the_proxies_of_a_run(tmp_path):
    async def prepare(lab):
        proxies = [await lab.proxy(f"203.0.113.{90 + i}") for i in range(3)]
        lab.confirm_429 = 1000
        return proxies

    run, stats, jobs = lab_run(tmp_path, prepare)
    assert run.working == set(jobs) and stats.fakes == 0 and stats.tampered == 0  # not learned as dead
    assert run.states[CONFIRM] == {"unavailable:target_rate_limited": 3}
    rows = json.loads((tmp_path / "run" / "proxies.json").read_text())
    from proxyscraper.publish import meets_requirements
    assert not any(meets_requirements(row) for row in rows)  # held back from the published list


def test_a_proxy_that_hangs_up_without_an_answer_is_no_answer_not_bad_status():
    async def scenario(lab, c):
        return await all_checks(c, await lab.proxy(EXIT, hangs_up_on_second=True))

    _, checks = in_lab(scenario)
    assert states(checks)[CONFIRM] == (FAILED, "no_answer")


def test_a_bare_429_without_rate_limit_headers_stays_the_proxys_bad_status():
    """A 429 without the target's rate-limit headers may be the proxy's own – it says something about the proxy."""
    async def scenario(lab, c):
        proxy = await lab.proxy(EXIT)
        lab.confirm_429 = 2
        lab.rate_limited_reply = b"HTTP/1.1 429 Too Many Requests\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
        return await all_checks(c, proxy)

    _, checks = in_lab(scenario, controls=False)
    assert states(checks)[CONFIRM] == (FAILED, "bad_status")


def test_retry_after_is_read_in_seconds_and_capped():
    assert ck.retry_after(b"HTTP/1.1 429 Too Many Requests\r\nretry-after: 1") == 1.0
    assert ck.retry_after(b"HTTP/1.1 429 Too Many Requests\r\nRetry-After: 120") == ck.RETRY_AFTER_MAX
    assert ck.retry_after(b"HTTP/1.1 429 Too Many Requests\r\nRetry-After: Wed, 21 Oct 2026 07:28:00 GMT") == 1.0
    assert ck.retry_after(b"HTTP/1.1 429 Too Many Requests") == ck.RETRY_AFTER_DEFAULT


def test_the_pacing_spaces_one_exit_only_and_leaves_unknown_exits_alone():
    async def go():
        pacer = ck.ExitPacer(rate=10.0, max_wait=0.25)
        loop = asyncio.get_running_loop()
        start = loop.time()
        await asyncio.gather(pacer.wait("203.0.113.1"), pacer.wait("203.0.113.2"), pacer.wait(""), pacer.wait(""))
        unrelated = loop.time() - start
        start = loop.time()
        await asyncio.gather(*(pacer.wait("203.0.113.3") for _ in range(3)))  # slots at 0, .1, .2 s
        shared = loop.time() - start
        return unrelated, shared

    unrelated, shared = asyncio.run(go())
    assert unrelated < 0.05
    assert 0.15 <= shared < 0.45  # the last slot is .2 s away; the loop clock may round a hair under it


def test_a_slot_further_away_than_max_wait_is_refused_at_once_and_not_reserved():
    """An overbooked exit used to make every later request wait the full max_wait and then go all at once."""
    async def go():
        pacer = ck.ExitPacer(rate=10.0, max_wait=0.25)
        loop = asyncio.get_running_loop()
        start = loop.time()
        granted = await asyncio.gather(*(pacer.wait("203.0.113.4") for _ in range(10)))
        elapsed = loop.time() - start
        await asyncio.sleep(0.1)  # the refused ones reserved nothing: the next slot is .1 s after the last one
        start = loop.time()
        again = await pacer.wait("203.0.113.4")
        return granted, elapsed, again, loop.time() - start

    granted, elapsed, again, waited = asyncio.run(go())
    assert granted == [True, True, True] + [False] * 7  # slots at 0, .1, .2 s; .3 s is beyond max_wait
    assert elapsed < 0.4
    assert again is True and waited < 0.2


def test_an_overbooked_exit_ip_is_rate_limited_at_once_without_a_request():
    """A backconnect pool: hundreds of ports leaving through one exit IP. Only as many second requests go out
    as the exit's rate allows; the rest are unavailable:target_rate_limited at once, with no request sent."""
    rate, max_wait = 20.0, 0.3

    async def scenario(lab, c):
        c.pacer = ck.ExitPacer(rate=rate, max_wait=max_wait)
        lab.confirm_rate_limit = int(rate)  # like httpbin: more than this per second from one exit is a 429
        # 200 proxies that passed the basic check, as 20 ports on each of 10 machines: a backconnect pool keeps
        # few file descriptors open in the lab (macOS runners allow 256)
        passed = [(await c.check_detailed(f"http {await lab.proxy(SHARED_EXIT)}"))[0] for _ in range(10)]
        results = [dataclasses.replace(r, checks=dict(r.checks)) for r in passed for _ in range(20)]
        loop = asyncio.get_running_loop()
        start, before = loop.time(), len(lab.confirm_requests)  # the checker fetched the reference page directly
        await asyncio.gather(*(c.confirm(r) for r in results))
        return ([r.checks[CONFIRM] for r in results], loop.time() - start, lab.confirm_requests[before:],
                lab.rate_limited)

    confirms, elapsed, requests, rate_limited = in_lab(scenario, timeout=3.0)
    assert elapsed < max_wait + 2.0  # bounded: nobody waits beyond max_wait and then goes anyway
    assert rate_limited == 0  # no request beyond the rate reached the target
    assert len(requests) == sum(1 for check in confirms if check.state == PASSED)
    overflow = [check for check in confirms if check.state != PASSED]
    assert len(overflow) > 150
    assert all((check.state, check.reason) == (UNAVAILABLE, "target_rate_limited") for check in overflow)
    assert all(check.limits == ck.UNCONFIRMED_LIMITS for check in overflow)


def test_a_proxy_that_hangs_up_on_the_first_request_is_no_answer():
    async def scenario(lab, c):
        async def hang_up(reader, writer):
            await reader.readuntil(b"\r\n\r\n")
            writer.close()

        server = await asyncio.start_server(hang_up, "127.0.0.1", 0)
        try:
            return await c.check_detailed(f"http 127.0.0.1:{server.sockets[0].getsockname()[1]}")
        finally:
            server.close()

    result, basic = in_lab(scenario, controls=False)
    assert result is None and (basic.state, basic.reason) == (FAILED, "no_answer")
