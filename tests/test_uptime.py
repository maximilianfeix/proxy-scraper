import json
from datetime import datetime, timedelta, timezone

from proxyscraper import publish
from tests.test_publish import run_dir

NOW = datetime(2026, 9, 27, 12, 17, tzinfo=timezone.utc)
FAST = "socks5://2.2.2.2:1080"


def last_run():
    return (NOW - timedelta(hours=1)).isoformat()


def hourly_history(tmp_path, runs):
    """`runs` past hourly runs, the newest one hour before NOW"""
    path = tmp_path / "history.json"
    path.write_text(json.dumps([{"updated": (NOW - timedelta(hours=runs - i)).isoformat(), "total": 100, "run_hours": 1}
                                for i in range(runs)]))
    return path


def publish_once(tmp_path, name, history, seen=None, streaks=None, now=NOW):
    out = tmp_path / name
    publish.publish(run_dir(tmp_path), out, minimum=2, now=now, history=history, seen=seen, streaks=streaks)
    return out, {r["url"]: r for r in json.loads((out / "proxies.json").read_text())}


def test_uptime_counts_the_runs_a_proxy_was_listed_in(tmp_path):
    history = hourly_history(tmp_path, 47)  # with this run: 48 runs, 24 of them in the last day
    seen = tmp_path / "seen.json"
    # listed in every other run of the last two days
    bits = int("10" * 24, 2)  # bit 0 = the run before this one
    seen.write_text(json.dumps({"last_run": last_run(), "proxies": {FAST: {"first_seen": "2026-09-25T13:17:00+00:00",
                                                               "bits": format(bits, "x")}}}))
    _, rows = publish_once(tmp_path, "public", history, seen)
    fast = rows[FAST]
    # this run plus 11 of the 23 earlier runs in the last day; over all 48 runs the oldest listed one drops out
    assert fast["uptime_24h"] == round(100 * 12 / 24)
    assert fast["uptime_7d"] == round(100 * 24 / 48)
    assert fast["first_seen"] == "2026-09-25T13:17:00+00:00"
    new = rows["http://1.1.1.2:80"]
    assert new["first_seen"] == NOW.isoformat(timespec="seconds")
    assert new["uptime_24h"] == round(100 / 24)


def test_proxies_missing_this_run_are_remembered_until_they_fall_out_of_the_window(tmp_path):
    history = hourly_history(tmp_path, 3)
    seen = tmp_path / "seen.json"
    old = publish.UPTIME_RUNS - 1
    seen.write_text(json.dumps({"last_run": last_run(), "proxies": {
        "http://7.7.7.7:80": {"first_seen": "2026-09-27T09:17:00+00:00", "bits": "1"},
        "http://8.8.8.8:80": {"first_seen": "2026-09-20T09:17:00+00:00", "bits": format(1 << old, "x")}}}))
    out, _ = publish_once(tmp_path, "public", history, seen)
    kept = json.loads((out / "seen.json").read_text())["proxies"]
    assert kept["http://7.7.7.7:80"]["bits"] == "2"  # shifted by one run, not listed this time
    assert "http://8.8.8.8:80" not in kept           # its only run is now older than the window
    assert kept[FAST]["bits"] == "1"


def test_without_seen_json_the_streaks_seed_the_uptime(tmp_path):
    history = hourly_history(tmp_path, 23)
    streaks = tmp_path / "streaks.json"
    streaks.write_text(json.dumps({FAST: 23}))
    _, rows = publish_once(tmp_path, "public", history, streaks=streaks)
    assert rows[FAST]["uptime_24h"] == 100 and rows[FAST]["uptime_7d"] == 100
    assert rows[FAST]["first_seen"] == (NOW - timedelta(hours=23)).isoformat(timespec="seconds")
    assert rows["http://1.1.1.0:80"]["uptime_7d"] == round(100 / 24)


def test_stable_list_needs_ninety_percent_over_the_week(tmp_path):
    history = hourly_history(tmp_path, 29)
    seen = tmp_path / "seen.json"
    seen.write_text(json.dumps({"last_run": last_run(), "proxies": {FAST: {"first_seen": "2026-09-27T00:00:00+00:00",
                                                               "bits": format((1 << 29) - 1, "x")},
                                                        "http://1.1.1.0:80": {"first_seen": "2026-09-27T00:00:00+00:00",
                                                                              "bits": format((1 << 23) - 1, "x")}}}))
    out, rows = publish_once(tmp_path, "public", history, seen)
    assert rows["http://1.1.1.0:80"]["uptime_7d"] == 80  # 24 of 30 runs
    assert (out / "stable.txt").read_text() == FAST + "\n"
    assert "stable.txt" in (out / "README.md").read_text()


def test_broken_seen_json_falls_back_to_the_streaks(tmp_path):
    history = hourly_history(tmp_path, 30)
    seen = tmp_path / "seen.json"
    seen.write_text(json.dumps({"proxies": {FAST: {"bits": "zz"}, "x": 5}}))
    streaks = tmp_path / "streaks.json"
    streaks.write_text(json.dumps({FAST: 30}))
    _, rows = publish_once(tmp_path, "public", history, seen, streaks)
    assert rows[FAST]["uptime_7d"] == 100


def test_seen_json_from_a_different_history_is_not_trusted(tmp_path):
    # seen.json was written after a different run than the last one in the history: the bits don't line up
    history = hourly_history(tmp_path, 26)
    seen = tmp_path / "seen.json"
    seen.write_text(json.dumps({"last_run": "2026-09-27T02:17:00+00:00",
                                "proxies": {FAST: {"first_seen": "2026-09-27T00:00:00+00:00", "bits": "1f"}}}))
    streaks = tmp_path / "streaks.json"
    streaks.write_text(json.dumps({FAST: 1}))
    _, rows = publish_once(tmp_path, "public", history, seen, streaks)
    assert rows[FAST]["uptime_7d"] == round(100 * 2 / 27)  # seeded from the streak: this run and the one before


def test_a_young_history_does_not_make_everything_stable(tmp_path):
    # a fresh fork: no history, no seen.json – one run is not a week of uptime
    out, rows = publish_once(tmp_path, "public", None)
    assert all(r["uptime_7d"] < publish.STABLE_UPTIME for r in rows.values())
    assert (out / "stable.txt").read_text() == ""


def test_the_csv_has_the_uptime_too(tmp_path):
    history = hourly_history(tmp_path, 3)
    out, _ = publish_once(tmp_path, "public", history)
    import csv
    with (out / "proxies.csv").open(newline="", encoding="utf-8") as fh:
        row = next(r for r in csv.DictReader(fh) if r["url"] == FAST)
    assert row["uptime_7d"] and row["first_seen"] and "uptime_24h" in row
