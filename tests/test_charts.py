import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

from proxyscraper import charts, publish
from tests.test_publish import run_dir

NOW = datetime(2026, 9, 27, 12, 17, tzinfo=timezone.utc)
SVG = "{http://www.w3.org/2000/svg}"


def run(hours_ago, total, minutes=0):
    by_type = {"http": total // 2, "socks4": total // 4, "socks5": total - total // 2 - total // 4}
    when = NOW - timedelta(hours=hours_ago, minutes=minutes)
    return {"updated": when.isoformat(), "total": total, "by_type": by_type}


def texts(svg):
    return [t.text for t in ET.fromstring(svg).iter(f"{SVG}text")]


def test_trend_shows_the_latest_total_and_one_area_per_protocol():
    runs = [run(h, 1000 + h) for h in range(200, -1, -1)]
    for theme in charts.THEMES:
        svg = charts.trend_svg(runs, NOW, theme)
        root = ET.fromstring(svg)
        assert "1,000" in texts(svg)  # the newest run
        assert len(list(root.iter(f"{SVG}polygon"))) == len(charts.PROXY_TYPES)


def test_only_the_last_week_counts_and_close_runs_count_once():
    runs = [run(24 * 8, 5000), run(3, 100), run(2, 200), run(2, 900, minutes=-10)]  # 10 min after the 2 h run
    points = charts.recent_runs(runs, NOW)
    assert [r["total"] for _, r in points] == [100, 900]


def test_a_fresh_history_gets_a_note_instead_of_a_chart():
    svg = charts.trend_svg([run(0, 50)], NOW)
    assert "The chart fills up with the next runs" in texts(svg)
    assert charts.trend_svg([{"updated": "garbage", "total": 1}], NOW)  # broken entries don't crash it


def test_countries_are_the_top_ten_biggest_first():
    svg = charts.countries_svg({f"C{i}": i for i in range(1, 15)}, "light")
    shown = [t for t in texts(svg) if t.startswith("C")]
    assert shown == [f"C{i}" for i in range(14, 4, -1)]


def test_countries_get_their_names():
    shown = texts(charts.countries_svg({"US": 9, "NL": 5, "XK": 1}))
    assert {"United States", "Netherlands", "XK"} <= set(shown)


def test_publish_writes_the_charts_for_both_themes(tmp_path):
    out = tmp_path / "public"
    publish.publish(run_dir(tmp_path), out, minimum=2, now=NOW)
    for name in ("chart-dark.svg", "chart-light.svg", "countries-dark.svg", "countries-light.svg"):
        ET.fromstring((out / name).read_text(encoding="utf-8"))
