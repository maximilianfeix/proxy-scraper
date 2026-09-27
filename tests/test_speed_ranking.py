"""Download speed in the choice of proxy (#186): a quick answer to one tiny request says little about loading a
page – in a test on the live list, the 25 proxies with the best latency loaded 8 of 50 pages, the 25 that downloaded
fastest in the last run 33 of 50."""

import random

from proxyscraper import api, live_proxies
from proxyscraper.agent import _as_result
from proxyscraper.checker import CheckResult
from proxyscraper.server import ProxyPool
from proxyscraper.server.pool import page_ms

from .test_live_api import ROWS, STATS, fetch_from


def result(n, latency, speed=None, https=True):
    proxy = f"10.0.0.{n}:80"
    return CheckResult(f"http {proxy}", "http", proxy, latency, "9.9.9.9", https=https, speed_kbps=speed)


def test_a_proxy_that_downloads_fast_beats_one_that_only_answers_fast():
    quick_ping, fast_download = result(1, 100), result(2, 400, speed=500)
    assert page_ms(fast_download, typical_kbps=100) < page_ms(quick_ping, typical_kbps=100)
    pool = ProxyPool([quick_ping, fast_download], strategy="fastest")
    assert pool.pick(set()).result is fast_download


def test_the_weighted_choice_leans_to_the_fast_downloader():
    pool = ProxyPool([result(1, 100), result(2, 400, speed=500)], rng=random.Random(1))
    picks = [pool.pick(set()).result.proxy for _ in range(1000)]
    assert picks.count("10.0.0.2:80") > 700


def test_without_any_speed_data_latency_decides_as_before():
    pool = ProxyPool([result(1, 400), result(2, 100)], strategy="fastest")
    assert pool.pick(set()).result.latency == 100


def test_the_live_list_brings_its_speed_into_the_pool():
    row = {"ptype": "http", "proxy": "1.2.3.4:80", "latency": 100, "https": True, "speed_kbps": 250}
    assert _as_result(row).speed_kbps == 250
    assert _as_result({**row, "speed_kbps": "fast"}).speed_kbps is None


def test_live_proxies_put_the_measured_fast_ones_first(monkeypatch):
    rows = [dict(r) for r in ROWS]
    rows[0]["speed_kbps"] = 400  # socks5, latency 300 – the slowest to answer, the only one that downloaded
    monkeypatch.setattr(api, "_live_fetch", fetch_from({"proxies.json": rows, "stats.json": STATS}))
    # the socks4 one answers faster but got no download through in the speed step
    assert [p.url for p in live_proxies(https=True)] == ["socks5://1.1.1.1:1080", "socks4://3.3.3.3:4145"]


def test_proxies_the_speed_step_never_tried_count_as_typical_not_slow():
    # it only measures HTTPS-capable ones – a plain-HTTP-only proxy wasn't slow, it just wasn't measured
    plain_only, measured = result(1, 50, https=False), result(2, 900, speed=100)
    pool = ProxyPool([plain_only, measured], strategy="fastest")
    assert pool.pick(set()).result is plain_only
    assert pool.pick(set(), tls=True).result is measured


def published(n, latency, speed=None, https=True, ptype="http"):
    row = {"proxy": f"10.0.0.{n}:80", "ptype": ptype, "url": f"{ptype}://10.0.0.{n}:80", "latency": latency,
           "https": https, "country": "DE", "exit_ip": f"10.0.0.{n}", "anonymity": "elite"}
    return {**row, "speed_kbps": speed} if speed else row


def test_the_published_lists_start_with_the_ones_that_load_pages_fastest(tmp_path):
    import json

    from proxyscraper import publish

    (tmp_path / "proxies.json").write_text(json.dumps([published(1, 100), published(2, 400, speed=500)]))
    assert [r["proxy"] for r in publish.load_rows(tmp_path)] == ["10.0.0.2:80", "10.0.0.1:80"]


def test_landing_pages_list_the_best_first(tmp_path):
    from datetime import datetime, timezone

    from proxyscraper import pages

    pages.write_pages([published(1, 100), published(2, 400, speed=500)], tmp_path, datetime.now(timezone.utc))
    assert (tmp_path / "country" / "de" / "proxies.txt").read_text().splitlines()[0] == "http://10.0.0.2:80"


def test_the_csv_comes_in_the_same_order_as_the_json(tmp_path):
    import csv
    import json

    from proxyscraper import publish
    from proxyscraper.output import ResultWriter

    results = [CheckResult(f"http 1.1.1.{i}:80", "http", f"1.1.1.{i}:80", 100 * (i + 1), "9.9.9.9", True, "elite", "DE")
               for i in range(3)]
    ResultWriter(run_dir=tmp_path / "run").finalize(results)
    rows = json.loads((tmp_path / "run" / "proxies.json").read_text())
    rows[2]["speed_kbps"] = 900  # the slowest to answer downloads fastest
    (tmp_path / "run" / "proxies.json").write_text(json.dumps(rows))
    publish.publish(tmp_path / "run", tmp_path / "out", minimum=1)
    order = [r["proxy"] for r in json.loads((tmp_path / "out" / "proxies.json").read_text())]
    with (tmp_path / "out" / "proxies.csv").open(newline="") as fh:
        assert [r["proxy"] for r in csv.DictReader(fh)] == order and order[0] == "1.1.1.2:80"


def test_the_mcp_tools_list_best_first_too():
    from proxyscraper.agent import select

    rows = [published(1, 100), published(2, 400, speed=500)]
    assert [r["proxy"] for r in select(rows)] == ["10.0.0.2:80", "10.0.0.1:80"]
