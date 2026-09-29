"""Best first on the live list counts how likely a proxy is still up: 25 % of new ones are listed again an hour
later, 99 % of those listed for a day (ranking.SURVIVAL)."""

import json
from datetime import datetime, timezone

from proxyscraper import publish, ranking

from .test_publish import run_dir


def row(n, latency, streak=None, **extra):
    r = {"url": f"http://1.1.1.{n}:80", "latency": latency, "ptype": "http", **extra}
    if streak is not None:
        r["streak"] = streak
    return r


def test_survival_grows_with_the_streak_and_is_certain_without_one():
    shares = [ranking.survival(n) for n in (1, 2, 3, 6, 12, 24, 500)]
    assert shares == sorted(shares) and shares[0] == 0.25 and shares[-1] == 0.99
    assert ranking.survival(5) == ranking.survival(3)  # buckets as measured
    for missing in (None, 0, -1, "7", True):  # own scans, broken rows
        assert ranking.survival(missing) == 1.0


def test_a_proxy_listed_for_a_day_beats_a_slightly_faster_new_one():
    rows = [row(1, 100, streak=1), row(2, 300, streak=30)]
    assert [r["url"] for r in ranking.best_first(rows)] == ["http://1.1.1.2:80", "http://1.1.1.1:80"]


def test_a_much_faster_new_proxy_still_wins():
    rows = [row(1, 100, streak=1), row(2, 2000, streak=30)]
    assert ranking.best_first(rows)[0]["url"] == "http://1.1.1.1:80"


def test_without_streaks_it_is_the_speed_ranking_as_before():
    rows = [row(1, 300), row(2, 100), row(3, 200)]
    assert [r["latency"] for r in ranking.best_first(rows)] == [100, 200, 300]
    assert ranking.expected_ms(250, None, None, None) == ranking.page_ms(250, None, None, None)


def test_publish_ranks_by_the_streaks_of_this_run(tmp_path):
    """The rows are ranked once more after the streaks are known: the proxy that was already on the list moves up."""
    run = run_dir(tmp_path)
    now = datetime(2026, 9, 24, 18, 0, tzinfo=timezone.utc)
    # 1.1.1.0 answers in 100 ms, the socks5 one in 50 – but 1.1.1.0 has been listed for the last 40 runs
    streaks = tmp_path / "streaks.json"
    streaks.write_text(json.dumps({"http://1.1.1.0:80": 40}), encoding="utf-8")
    history = tmp_path / "history.json"
    history.write_text(json.dumps([{"updated": "2026-09-24T17:00:00+00:00", "total": 4, "run_hours": 1}]),
                       encoding="utf-8")
    out = tmp_path / "public"
    assert publish.publish(run, out, minimum=2, now=now, history=history, streaks=streaks) == 0
    first = (out / "all.txt").read_text(encoding="utf-8").splitlines()[0]
    assert first == "http://1.1.1.0:80"
    rows = json.loads((out / "proxies.json").read_text(encoding="utf-8"))
    assert rows[0]["streak"] == 41
