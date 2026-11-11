"""When httpbin.org's rate limit holds a proxy's second request back, the confirm runs against an IP echo
(ipv4.icanhazip.com) and the content check against a static page (example.com, info.cern.ch in reserve) – the
same proof, another target, recorded as such. Against the lab on localhost (tests/lab.py)."""

import asyncio
import json

from proxyscraper import checker as ck
from proxyscraper.checkstate import BASIC, CONFIRM, CONTENT, FAILED, HTTPS, PASSED, UNAVAILABLE
from proxyscraper.options import RunOptions
from tests.lab import INJECTED, Lab
from tests.test_check_states import EXIT, all_checks, lab_run, states

OTHER_EXIT = "203.0.113.21"


def in_lab(scenario, **checker_options):
    async def go():
        async with Lab() as lab:
            lab.confirm_429 = 1_000_000  # httpbin refuses every request with its rate-limit headers
            return await scenario(lab, await lab.checker(**checker_options))
    return asyncio.run(go())


def test_a_rate_limited_proxy_passes_via_the_fallback_targets_and_says_so():
    async def scenario(lab, c):
        return await all_checks(c, await lab.proxy(EXIT)), lab

    (result, checks), lab = in_lab(scenario, fallback=True)
    assert states(checks) == {BASIC: (PASSED, ""), CONFIRM: (PASSED, ""), CONTENT: (PASSED, ""), HTTPS: (PASSED, "")}
    assert checks[CONFIRM].target == f"localhost:{lab.ip_echo_port}"
    assert checks[CONFIRM].data == {"exit_ip": EXIT}
    assert checks[CONTENT].target == f"localhost:{lab.page_port}/"
    assert checks[CONTENT].data["bytes"] == len(lab.fallback_page)
    # the IP echo shows no request headers: anonymity stays unknown instead of being guessed
    assert result.anonymity == ""
    assert "anonymity" in checks[CONFIRM].limits
    assert lab.fallback_requests == 2


def test_another_exit_ip_at_the_fallback_is_a_mismatch():
    async def scenario(lab, c):
        return await all_checks(c, await lab.proxy(EXIT, second_exit_ip=OTHER_EXIT)), lab

    (_, checks), lab = in_lab(scenario, fallback=True)
    assert states(checks)[CONFIRM] == (FAILED, "exit_ip_mismatch")
    assert checks[CONFIRM].target == f"localhost:{lab.ip_echo_port}"
    assert checks[CONFIRM].data == {"exit_ip": EXIT, "second_exit_ip": OTHER_EXIT}
    assert checks[CONFIRM].limits == ck.MISMATCH_LIMITS


def test_a_proxy_that_changes_the_fallback_page_fails_the_content_check():
    async def scenario(lab, c):
        return await all_checks(c, await lab.proxy(EXIT, rewrite=lambda body: INJECTED)), lab

    (_, checks), lab = in_lab(scenario, fallback=True)
    assert states(checks)[CONFIRM] == (PASSED, "")
    assert states(checks)[CONTENT] == (FAILED, "content_mismatch")
    assert checks[CONTENT].target == f"localhost:{lab.page_port}/"
    assert checks[CONTENT].data["bytes"] == len(INJECTED) and checks[CONTENT].data["script_tags"] == 1


def test_without_a_fallback_reference_the_content_check_stays_rate_limited():
    async def scenario(lab, c):
        lab.page_down = False  # the page is back, but the run started without a reference
        return await all_checks(c, await lab.proxy(EXIT))

    async def go():
        async with Lab() as lab:
            lab.confirm_429 = 1_000_000
            lab.page_down = True  # the fallback page didn't answer when the run started
            return await scenario(lab, await lab.checker(fallback=True))

    _, checks = asyncio.run(go())
    assert states(checks)[CONFIRM] == (PASSED, "")
    assert states(checks)[CONTENT] == (UNAVAILABLE, "target_rate_limited")


def test_a_fallback_target_that_is_down_says_nothing_about_the_proxy():
    async def scenario(lab, c):
        proxy = await lab.proxy(EXIT)
        lab.ip_echo_down = True
        return await all_checks(c, proxy), lab

    (_, checks), lab = in_lab(scenario, fallback=True)
    assert states(checks)[CONFIRM] == (UNAVAILABLE, "target_unreachable")
    assert checks[CONFIRM].target == f"localhost:{lab.ip_echo_port}"


def test_without_fallback_targets_a_rate_limited_check_stays_unavailable():
    async def scenario(lab, c):
        return await all_checks(c, await lab.proxy(EXIT))

    _, checks = in_lab(scenario)
    assert states(checks)[CONFIRM] == (UNAVAILABLE, "target_rate_limited")
    assert states(checks)[CONTENT] == (UNAVAILABLE, "target_rate_limited")


def test_an_answering_httpbin_leaves_the_fallback_targets_alone():
    async def go():
        async with Lab() as lab:
            c = await lab.checker(fallback=True)
            return await all_checks(c, await lab.proxy(EXIT)), lab

    (result, checks), lab = asyncio.run(go())
    assert states(checks)[CONFIRM] == (PASSED, "") and states(checks)[CONTENT] == (PASSED, "")
    assert checks[CONFIRM].target == f"localhost:{lab.confirm_port}"
    assert checks[CONTENT].target == f"localhost:{lab.confirm_port}/html"
    assert result.anonymity == "elite" and checks[CONFIRM].limits == ""
    assert lab.fallback_requests == 0


def test_a_run_records_the_fallback_target_in_its_results(tmp_path):
    async def prepare(lab):
        lab.confirm_429 = 1_000_000
        return [await lab.proxy(f"203.0.113.{60 + i}") for i in range(3)]

    run, _, jobs = lab_run(tmp_path, prepare, fallback=True)
    assert run.working == set(jobs)
    assert run.states[CONFIRM] == {"passed": 3} and run.states[CONTENT] == {"passed": 3}
    rows = json.loads((tmp_path / "run" / "proxies.json").read_text())
    assert {row["checks"]["confirm"]["target"].split(":")[0] for row in rows} == {"localhost"}
    assert all(row["checks"]["confirm"]["target"] != row["checks"]["content"]["target"] for row in rows)
    from proxyscraper.publish import meets_requirements
    assert all(meets_requirements(row) for row in rows)  # confirmed via the fallback: listed again


# --------------------------------------------------------------------------- choosing the fallback targets at start

IP_ECHO_IP, EXAMPLE_IP, CERN_IP = "198.51.100.1", "198.51.100.2", "198.51.100.3"
RESOLVED = {"ipv4.icanhazip.com": IP_ECHO_IP, "example.com": EXAMPLE_IP, "info.cern.ch": CERN_IP}


def choose(pages):
    """fallback_targets with DNS and the direct fetches faked: pages maps a URL to (status, body)."""
    asked = []

    async def resolve(host):
        return RESOLVED.get(host)

    async def fetch(url, **kwargs):
        asked.append(url)
        if url not in pages:
            raise OSError("unreachable")
        status, body = pages[url]
        return status, {}, body

    return asyncio.run(ck.fallback_targets(1.0, fetch=fetch, resolve=resolve)), asked


def test_the_fallback_targets_are_the_ip_echo_and_example_com_with_a_direct_reference():
    (confirm, content), _ = choose({"http://ipv4.icanhazip.com/": (200, b"192.0.2.7\n"),
                                    "https://example.com/": (200, b"<html>example</html>")})
    assert (confirm.host, confirm.ip, confirm.port, confirm.path) == ("ipv4.icanhazip.com", IP_ECHO_IP, 80, "/")
    assert (content.host, content.ip, content.port, content.path) == ("example.com", EXAMPLE_IP, 80, "/")
    assert content.reference == ck.page_hash(b"<html>example</html>")


def test_info_cern_ch_is_the_reserve_when_example_com_does_not_answer():
    (_, content), asked = choose({"https://example.com/": (503, b"busy"),
                                  "https://info.cern.ch/": (200, b"<html>cern</html>")})
    assert (content.host, content.ip) == ("info.cern.ch", CERN_IP)
    assert content.reference == ck.page_hash(b"<html>cern</html>")
    assert asked.index("https://example.com/") < asked.index("https://info.cern.ch/")  # example.com first


def test_no_reference_and_no_ip_echo_mean_no_fallback_targets():
    (confirm, content), _ = choose({"http://ipv4.icanhazip.com/": (200, b"<html>not an address</html>")})
    assert confirm is None and content is None


def test_run_json_names_the_fallback_targets_of_the_run(tmp_path):
    from types import SimpleNamespace

    from proxyscraper.app import Run

    async def prepare(lab):
        return [await lab.proxy(EXIT)]

    run, stats, jobs = lab_run(tmp_path, prepare)
    app = Run(RunOptions(no_geo=True), show_banner=False)
    c = SimpleNamespace(judge=None, failures={}, confirm_fallback=None, content_fallback=None)
    app.checker, app.judges = c, [SimpleNamespace(judge=SimpleNamespace(host="checkip.amazonaws.com"))]
    assert app.summary(jobs, run, stats, run.results)["targets"]["confirm_fallback"] is None
    c.confirm_fallback = ck.SecondTarget("ipv4.icanhazip.com", IP_ECHO_IP)
    c.content_fallback = ck.SecondTarget("info.cern.ch", CERN_IP, reference=b"x")
    targets = app.summary(jobs, run, stats, run.results)["targets"]
    assert (targets["confirm_fallback"], targets["content_fallback"]) == ("ipv4.icanhazip.com", "info.cern.ch")


def test_the_diagnosis_says_the_anonymity_is_unknown_after_a_fallback_confirm():
    from proxyscraper import verify
    from proxyscraper.checkstate import Check

    result = ck.CheckResult("http 127.0.0.1:8080", "http", "127.0.0.1:8080", 100, EXIT)
    report = verify.Report(result.key, {CONFIRM: Check(PASSED, "", "ipv4.icanhazip.com:80",
                                                       limits=ck.FALLBACK_CONFIRM_LIMITS)}, result)
    assert verify._measured(report, CONFIRM) == "same exit IP on a second site, anonymity: unknown"
