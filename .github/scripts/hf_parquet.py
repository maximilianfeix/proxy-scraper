"""Turns a daily snapshot (proxies-YYYY-MM-DD.json.gz) into Parquet for the Hugging Face dataset.

The Hub reads every day's file as one table, so all days must have exactly the same columns: a field that
appears later (speed_kbps) or a site added to the checks (discord) made load_dataset fail. Hence one fixed
schema, and the site results as two lists instead of a struct that grows with every new site (#271).

    python .github/scripts/hf_parquet.py proxies-2026-10-06.json.gz proxies-2026-10-06.parquet 2026-10-06
"""

import gzip
import json
import sys

# column order of the Parquet files – the dataset card documents exactly these
COLUMNS = (
    ("url", "string"),
    ("ptype", "string"),
    ("proxy", "string"),
    ("exit_ip", "string"),
    ("country", "string"),
    ("asn", "int64"),
    ("org", "string"),
    ("hosting", "bool"),
    ("blocklisted", "bool"),
    ("anonymity", "string"),
    ("https", "bool"),
    ("latency", "int64"),
    ("speed_kbps", "int64"),
    ("works_on", "list<string>"),
    ("blocked_on", "list<string>"),
    ("streak", "int64"),
    ("uptime_24h", "int64"),
    ("uptime_7d", "int64"),
    ("first_seen", "string"),
    ("snapshot_date", "string"),
)


def _cast(value, kind):
    if value is None:
        return None
    if kind == "int64":
        return int(value)
    if kind == "bool":
        return bool(value)
    if kind == "string":
        return str(value)
    return value


def normalize(row: dict, snapshot_date: str) -> dict:
    """One proxies.json row -> exactly COLUMNS, in order; missing fields are None."""
    sites = row.get("sites") or {}
    derived = {
        "works_on": sorted(name for name, ok in sites.items() if ok is True),
        "blocked_on": sorted(name for name, ok in sites.items() if ok is False),
        "snapshot_date": snapshot_date,
    }
    unknown = ("asn", "org", "country", "anonymity", "exit_ip")  # the checks write 0 / "" when they don't know
    row = {**row, **{name: row.get(name) or None for name in unknown}}
    return {name: derived[name] if name in derived else _cast(row.get(name), kind) for name, kind in COLUMNS}


def schema():
    import pyarrow as pa

    types = {"string": pa.string(), "int64": pa.int64(), "bool": pa.bool_(), "list<string>": pa.list_(pa.string())}
    return pa.schema([(name, types[kind]) for name, kind in COLUMNS])


def convert(source, destination, snapshot_date: str) -> int:
    import pyarrow as pa
    import pyarrow.parquet as pq

    with gzip.open(source, "rt", encoding="utf-8") as handle:
        rows = json.load(handle)
    table = pa.Table.from_pylist([normalize(row, snapshot_date) for row in rows], schema=schema())
    pq.write_table(table, destination, compression="zstd")
    return len(rows)


if __name__ == "__main__":
    src, dst, day = sys.argv[1:]
    print(f"wrote {dst} with {convert(src, dst, day):,} rows")
