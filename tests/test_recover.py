"""Checks that recover from a lost connection instead of failing a working proxy for it – against the lab.

Free proxies that answered the basic check often lose the first connection of the next request (a SYN that
got lost, a first accept that never came through). Those requests are tried once more; failures that come
from an answer (another exit IP, a bad status, a changed page) are not.
"""

import asyncio

from proxyscraper import checker as ck
from proxyscraper.checkstate import CONFIRM, CONTENT, FAILED, PASSED
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
            await super().wait(exit_ip)

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
