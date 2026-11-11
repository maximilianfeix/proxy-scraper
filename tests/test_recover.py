"""Checks that recover instead of failing a working proxy – against the lab (tests/lab.py).

Free proxies that answered the basic check often lose the first connection of the next request (a SYN that
got lost, a first accept that never came through). Those requests are tried once more; failures that come
from an answer (another exit IP, a bad status, a changed page) are not. And an address whose port answers in
another protocol than its list says is tried in the other protocols on the same ip:port.
"""

import asyncio
import contextlib
from collections import Counter

from proxyscraper import checker as ck
from proxyscraper import output, pipeline
from proxyscraper.checkstate import CONFIRM, CONTENT, FAILED, PASSED
from proxyscraper.geo import GeoResolver
from proxyscraper.options import RunOptions
from proxyscraper.ui import CheckDashboard, LiveStats
from tests.lab import INJECTED, Lab

EXIT = "203.0.113.30"


def in_lab(scenario, **checker_options):
    async def go():
        async with Lab() as lab:
            return await scenario(lab, await lab.checker(**checker_options))
    return asyncio.run(go())


async def basic_and_confirm(c, proxy):
    result, _ = await c.check_detailed(f"http {proxy}")
    assert result is not None
    await c.confirm(result)
    return result


# --------------------------------------------------------------------------- lever 1: retry follow-up requests

def test_a_confirm_whose_first_connection_is_dropped_passes_on_the_retry():
    async def scenario(lab, c):
        proxy = await lab.proxy(EXIT, drops=[2])  # 1 = basic check, 2 = the first try of the confirm
        result = await basic_and_confirm(c, proxy)
        return result.checks[CONFIRM], lab.connections[proxy]

    confirm, connections = in_lab(scenario)
    assert (confirm.state, confirm.reason) == (PASSED, "")
    assert connections == 3


def test_a_confirm_that_gets_no_answer_in_time_passes_on_the_retry():
    async def scenario(lab, c):
        proxy = await lab.proxy(EXIT, stalls=[2])
        result = await basic_and_confirm(c, proxy)
        return result.checks[CONFIRM], lab.connections[proxy]

    confirm, connections = in_lab(scenario, timeout=1.0)
    assert confirm.state == PASSED and connections == 3


def test_a_content_check_whose_first_connection_is_dropped_passes_on_the_retry():
    async def scenario(lab, c):
        proxy = await lab.proxy(EXIT, drops=[3])  # basic, confirm, then the content request
        result = await basic_and_confirm(c, proxy)
        await c.tampers(result)
        return result.checks[CONTENT], lab.connections[proxy]

    content, connections = in_lab(scenario)
    assert content.state == PASSED and connections == 4


def test_a_proxy_that_keeps_dropping_the_confirm_is_tried_only_once_more():
    async def scenario(lab, c):
        proxy = await lab.proxy(EXIT, drops=[2, 3, 4, 5])
        result = await basic_and_confirm(c, proxy)
        return result.checks[CONFIRM], lab.connections[proxy]

    confirm, connections = in_lab(scenario)
    assert (confirm.state, confirm.reason) == (FAILED, "no_answer")
    assert connections == 3  # basic + two tries, no more


def test_a_wrong_exit_ip_is_not_retried():
    async def scenario(lab, c):
        proxy = await lab.proxy(EXIT, second_exit_ip="203.0.113.31")
        result = await basic_and_confirm(c, proxy)
        return result.checks[CONFIRM], lab.connections[proxy]

    confirm, connections = in_lab(scenario)
    assert (confirm.state, confirm.reason) == (FAILED, "exit_ip_mismatch")
    assert connections == 2


def test_a_bad_status_is_not_retried():
    async def scenario(lab, c):
        proxy = await lab.proxy(EXIT, only_first_target=True)
        result = await basic_and_confirm(c, proxy)
        return result.checks[CONFIRM], lab.connections[proxy]

    confirm, connections = in_lab(scenario)
    assert (confirm.state, confirm.reason) == (FAILED, "bad_status")
    assert connections == 2


def test_a_changed_page_is_not_retried():
    async def scenario(lab, c):
        proxy = await lab.proxy(EXIT, rewrite=lambda body: INJECTED)
        result = await basic_and_confirm(c, proxy)
        await c.tampers(result)
        return result.checks[CONTENT], lab.connections[proxy]

    content, connections = in_lab(scenario)
    assert (content.state, content.reason) == (FAILED, "content_mismatch")
    assert connections == 3


def test_the_retry_waits_for_its_slot_of_the_exit_ip():
    class Recording(ck.ExitPacer):
        def __init__(self):
            super().__init__()
            self.asked = []

        async def wait(self, exit_ip):
            self.asked.append(exit_ip)
            return await super().wait(exit_ip)

    async def scenario(lab, c):
        c.pacer = Recording()
        proxy = await lab.proxy(EXIT, drops=[2])
        await basic_and_confirm(c, proxy)
        return c.pacer.asked

    assert in_lab(scenario) == [EXIT, EXIT]


def test_only_transport_failures_are_retried():
    assert {"connect_timeout", "timeout", "connection_closed", "no_answer"} == ck.RETRY_REASONS


def test_follow_up_requests_connect_with_at_least_the_follow_up_connect_timeout():
    c = ck.Checker("127.0.0.1", set(), timeout=6, connect_timeout=3, detail_timeout=6, detail_connect_timeout=3)
    assert ck.FOLLOWUP_CONNECT_TIMEOUT == 6.0
    assert c.connect_timeout == 3 and c.followup_connect_timeout == 6
    # the time after the connect stays what it was: the longer connect is added on top
    assert c.followup_timeout == 9
    longer = ck.Checker("127.0.0.1", set(), timeout=10, connect_timeout=8)
    assert longer.followup_connect_timeout == 8 and longer.followup_timeout == 10


def test_a_slow_connect_fails_the_basic_check_but_not_a_follow_up_request(monkeypatch):
    async def slow_connect(host, port):
        await asyncio.sleep(0.3)
        return "reader", "writer"

    async def go():
        c = ck.Checker("127.0.0.1", set(), timeout=2, connect_timeout=0.1, followup_connect_timeout=1.0)
        monkeypatch.setattr(ck.asyncio, "open_connection", slow_connect)
        try:
            await c._connect("192.0.2.1:8080")
        except asyncio.TimeoutError:
            basic = "timeout"
        else:
            basic = "connected"
        follow_up = await c._connect("192.0.2.2:8080", detail=True)
        return basic, follow_up

    basic, follow_up = asyncio.run(go())
    assert basic == "timeout" and follow_up == ("reader", "writer")


# --------------------------------------------------------------------------- lever 3: the protocol the port speaks

def lab_run(tmp_path, prepare, opts=None):
    """A run over the jobs `prepare(lab)` returns ("type ip:port"); also returns every basic check it asked for."""
    async def go():
        async with Lab() as lab:
            c = await lab.checker()
            asked = []
            original = c.check

            async def counting(key):
                asked.append(key)
                return await original(key)

            c.check = counting
            jobs = await prepare(lab)
            stats = LiveStats(Counter(job.split(" ")[0] for job in jobs))
            writer = output.ResultWriter(run_dir=tmp_path / "run")
            options = opts or RunOptions(no_geo=True)
            dashboard = CheckDashboard(stats, writer.live_path, 4, options.details)
            run = await pipeline.run_checks(jobs, c, options, dashboard, writer, GeoResolver(enabled=False),
                                            live_factory=lambda _: contextlib.nullcontext())
            return run, asked, jobs
    return asyncio.run(go())


def test_an_address_listed_as_http_that_speaks_socks5_is_found_as_socks5(tmp_path):
    async def prepare(lab):
        return [f"http {await lab.socks_proxy(EXIT, version=5)}"]

    run, asked, jobs = lab_run(tmp_path, prepare)
    proxy = jobs[0].split(" ")[1]
    assert [r.key for r in run.results] == [f"socks5 {proxy}"]
    r = run.results[0]
    assert r.ptype == "socks5" and r.checks[CONFIRM].state == PASSED and r.checks[CONTENT].state == PASSED
    assert run.working == {f"socks5 {proxy}"}
    assert jobs[0] in run.checked and jobs[0] not in run.working  # as HTTP it doesn't work: the list was wrong
    assert asked == [f"http {proxy}", f"socks5 {proxy}"]  # found as SOCKS5, so SOCKS4 isn't tried


def test_an_address_listed_as_http_that_speaks_socks4_is_found_as_socks4(tmp_path):
    async def prepare(lab):
        return [f"http {await lab.socks_proxy(EXIT, version=4)}"]

    run, asked, jobs = lab_run(tmp_path, prepare)
    proxy = jobs[0].split(" ")[1]
    assert [r.key for r in run.results] == [f"socks4 {proxy}"]
    assert asked == [f"http {proxy}", f"socks5 {proxy}", f"socks4 {proxy}"]


def test_socks4_listed_as_socks5_is_found_as_socks4(tmp_path):
    async def prepare(lab):
        return [f"socks5 {await lab.socks_proxy(EXIT, version=4)}"]

    run, asked, jobs = lab_run(tmp_path, prepare)
    proxy = jobs[0].split(" ")[1]
    assert [r.key for r in run.results] == [f"socks4 {proxy}"]
    assert asked == [f"socks5 {proxy}", f"socks4 {proxy}"]


def test_no_second_check_when_the_other_type_is_already_a_candidate(tmp_path):
    async def prepare(lab):
        proxy = await lab.socks_proxy(EXIT, version=5)
        return [f"http {proxy}", f"socks5 {proxy}"]

    run, asked, jobs = lab_run(tmp_path, prepare, RunOptions(no_geo=True, concurrency=1))
    proxy = jobs[0].split(" ")[1]
    assert Counter(asked)[f"socks5 {proxy}"] == 1
    assert [r.key for r in run.results] == [f"socks5 {proxy}"]
    # SOCKS4 is still tried for the HTTP entry: it isn't a candidate, and the run doesn't know yet that SOCKS5 works
    assert Counter(asked)[f"socks4 {proxy}"] <= 1


def test_only_the_types_the_run_asked_for_are_tried(tmp_path):
    async def prepare(lab):
        return [f"http {await lab.socks_proxy(EXIT, version=5)}"]

    run, asked, jobs = lab_run(tmp_path, prepare, RunOptions(no_geo=True, types=["http", "socks4"]))
    proxy = jobs[0].split(" ")[1]
    assert run.results == [] and f"socks5 {proxy}" not in asked


def test_a_timeout_or_a_closed_port_is_not_a_reason_to_try_another_protocol(tmp_path):
    async def prepare(lab):
        return [f"http {await lab.proxy(EXIT, garbage=True)}", f"http {await lab.proxy(EXIT, answers_after=5)}",
                f"http {await lab.closed_port()}"]

    run, asked, jobs = lab_run(tmp_path, prepare)
    # only the page of its own (invalid_response) is tried as SOCKS: a port that answered, just not as an HTTP proxy
    garbage = jobs[0].split(" ")[1]
    assert sorted(asked) == sorted([*jobs, f"socks5 {garbage}", f"socks4 {garbage}"])
    assert run.results == []


def test_a_wrong_exit_ip_on_the_second_request_is_not_a_reason_to_try_another_protocol(tmp_path):
    async def prepare(lab):
        return [f"http {await lab.proxy(EXIT, second_exit_ip='203.0.113.31')}"]

    run, asked, jobs = lab_run(tmp_path, prepare)
    assert asked == jobs and run.states[CONFIRM] == {"failed:exit_ip_mismatch": 1}


def test_which_failures_point_to_another_protocol():
    assert ck.other_protocols("http", "no_answer") == ("socks5", "socks4")
    assert ck.other_protocols("http", "connection_closed") == ("socks5", "socks4")
    assert ck.other_protocols("http", "invalid_response") == ("socks5", "socks4")
    assert ck.other_protocols("http", "handshake_refused") == ("socks5", "socks4")
    assert ck.other_protocols("socks5", "handshake_refused") == ("socks4",)
    assert ck.other_protocols("socks4", "handshake_refused") == ("socks5",)
    for ptype, reason in [("http", "connect_timeout"), ("http", "connect_refused"), ("http", "known_unreachable"),
                          ("http", "timeout"), ("http", "bad_status"), ("http", "own_ip_exposed"),
                          ("socks5", "no_answer"), ("socks4", "connection_closed")]:
        assert ck.other_protocols(ptype, reason) == ()
