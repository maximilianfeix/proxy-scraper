"""Daily snapshots become Parquet with one fixed schema, so the Hub can read every day as one table (#271)."""

import gzip
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("hf_parquet", ROOT / ".github" / "scripts" / "hf_parquet.py")
hf_parquet = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hf_parquet)

NAMES = [name for name, _ in hf_parquet.COLUMNS]

TODAY = {"ptype": "http", "proxy": "1.2.3.4:80", "latency": 120, "exit_ip": "1.2.3.4", "https": True,
         "anonymity": "elite", "country": "DE", "targets": {}, "asn": 3320, "org": "Telekom", "hosting": False,
         "blocklisted": False, "speed_kbps": 900, "url": "http://1.2.3.4:80",
         "sites": {"google": True, "reddit": False, "discord": True}, "streak": 5,
         "first_seen": "2026-10-06T08:00:00+00:00", "uptime_24h": 100, "uptime_7d": 80}
# the first days had no speed, no uptime and only three sites
FIRST_DAYS = {"ptype": "socks5", "proxy": "5.6.7.8:1080", "latency": 300.0, "exit_ip": "5.6.7.8", "https": False,
              "anonymity": "elite", "country": "US", "url": "socks5://5.6.7.8:1080",
              "sites": {"google": False, "reddit": True, "amazon": False}, "streak": 1}


def test_every_row_has_the_same_columns_whatever_the_day():
    assert list(hf_parquet.normalize(TODAY, "2026-10-06")) == NAMES
    assert list(hf_parquet.normalize(FIRST_DAYS, "2026-09-27")) == NAMES
    assert list(hf_parquet.normalize({}, "2026-09-27")) == NAMES


def test_sites_become_two_lists_so_a_new_site_never_changes_the_schema():
    row = hf_parquet.normalize(TODAY, "2026-10-06")
    assert row["works_on"] == ["discord", "google"]
    assert row["blocked_on"] == ["reddit"]
    old = hf_parquet.normalize(FIRST_DAYS, "2026-09-27")
    assert old["works_on"] == ["reddit"] and old["blocked_on"] == ["amazon", "google"]
    assert hf_parquet.normalize({}, "2026-09-27")["works_on"] == []


def test_missing_fields_are_null_and_numbers_are_whole():
    row = hf_parquet.normalize(FIRST_DAYS, "2026-09-27")
    assert row["speed_kbps"] is None and row["uptime_7d"] is None and row["asn"] is None
    assert row["latency"] == 300 and isinstance(row["latency"], int)
    assert row["snapshot_date"] == "2026-09-27"
    assert "targets" not in row and "sites" not in row


def test_the_card_documents_exactly_the_parquet_columns():
    card = (ROOT / "docs" / "huggingface" / "README.md").read_text(encoding="utf-8")
    import re
    documented = re.findall(r"^\| `([a-z0-9_]+)` \|", card, re.MULTILINE)
    assert documented == NAMES


def test_the_workflows_use_the_script():
    daily = (ROOT / ".github" / "workflows" / "proxy-list.yml").read_text()
    rebuild = (ROOT / ".github" / "workflows" / "hf-rebuild.yml").read_text()
    assert ".github/scripts/hf_parquet.py" in daily and ".github/scripts/hf_parquet.py" in rebuild
    assert "pa.Table.from_pylist" not in daily  # no second, drifting copy of the conversion


def test_days_with_different_fields_write_the_same_schema(tmp_path):
    pq = pytest.importorskip("pyarrow.parquet")
    schemas = []
    for day, row in (("2026-09-27", FIRST_DAYS), ("2026-10-06", TODAY)):
        src = tmp_path / f"proxies-{day}.json.gz"
        with gzip.open(src, "wt", encoding="utf-8") as f:
            json.dump([row], f)
        dst = tmp_path / f"proxies-{day}.parquet"
        assert hf_parquet.convert(src, dst, day) == 1
        schemas.append(pq.read_schema(dst))
    assert schemas[0].equals(schemas[1])
    assert schemas[0].names == NAMES
