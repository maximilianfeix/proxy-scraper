"""Anbieter (ASN) offline: CSV mit Kommas im Namen, Rechenzentrum-Heuristik, Speichern, Filter."""

import asyncio
import gzip
from datetime import date

import pytest

from proxyscraper.asndb import AsnDB, ProviderLookup, is_hosting, load_asn_db
from proxyscraper.checker import CheckResult
from proxyscraper.cli import parse_args
from proxyscraper.options import Filters, RunOptions

CSV = '''1.0.0.0,1.0.0.255,13335,"Cloudflare, Inc."
1.0.4.0,1.0.7.255,38803,"Gtelecom Pty Ltd"
8.8.8.0,8.8.8.255,15169,"Google LLC"
2001:db8::,2001:db8::ffff,1,"IPv6"
9.9.9.0,9.9.9.255,kaputt,"x"
68.0.0.0,68.15.255.255,22773,"Cox Communications Inc."
'''


def big_csv(n=2000):
    return "\n".join(f'10.{i // 256}.{i % 256}.0,10.{i // 256}.{i % 256}.127,{i},"Org {i}"' for i in range(n)) + "\n"


def test_parse_and_lookup():
    db = AsnDB.from_csv(CSV, "2026-09")
    assert len(db) == 4
    cf = db.lookup("1.0.0.1")
    assert (cf.asn, cf.org, cf.hosting) == (13335, "Cloudflare, Inc.", True)  # Komma im Namen überlebt
    assert db.lookup("68.1.2.3").hosting is False
    assert db.lookup("8.8.8.8").org == "Google LLC" and db.lookup("8.8.8.8").hosting
    assert db.lookup("5.5.5.5") is None and db.lookup("kein.ip") is None


@pytest.mark.parametrize("org, expected", [
    ("Hetzner Online GmbH", True), ("DigitalOcean, LLC", True), ("Hangzhou Alibaba Advertising Co.,Ltd.", True),
    ("Performive LLC", True), ("Amazon.com, Inc.", True), ("GTHost", True), ("Deutsche Telekom AG", False),
    ("Cox Communications Inc.", False), ("Vodafone GmbH", False),
])
def test_hosting_heuristic(org, expected):
    assert is_hosting(org) is expected


def test_save_load_roundtrip_and_broken_files(tmp_path):
    db = AsnDB.from_csv(CSV, "2026-09")
    db.save(tmp_path / "asn.bin")
    again = AsnDB.load(tmp_path / "asn.bin")
    assert again.month == "2026-09" and again.lookup("1.0.0.1").org == "Cloudflare, Inc."
    data = (tmp_path / "asn.bin").read_bytes()
    (tmp_path / "asn.bin").write_bytes(data[:-3])
    assert AsnDB.load(tmp_path / "asn.bin") is None
    assert AsnDB.load(tmp_path / "fehlt.bin") is None


def test_download_new_month(tmp_path):
    async def fetch(url, timeout):
        assert "2026-09" in url
        return gzip.compress(big_csv().encode())

    db = asyncio.run(load_asn_db(tmp_path / "asn.bin", date(2026, 9, 25), fetch))
    assert db.month == "2026-09" and AsnDB.load(tmp_path / "asn.bin").month == "2026-09"


def test_annotate_and_no_datacenter_filter():
    lookup = ProviderLookup(AsnDB.from_csv(CSV, "2026-09"))
    dc = CheckResult("http 3.3.3.3:80", "http", "3.3.3.3:80", 100, "8.8.8.8")
    home = CheckResult("http 4.4.4.4:80", "http", "4.4.4.4:80", 100, "68.1.2.3")
    unknown = CheckResult("http 5.5.5.5:80", "http", "5.5.5.5:80", 100, "5.5.5.5")
    for r in (dc, home, unknown):
        lookup.annotate(r)
    assert (dc.asn, dc.hosting) == (15169, True) and home.hosting is False and unknown.hosting is None
    f = Filters(no_datacenter=True)
    assert not f.accepts(dc) and not f.may_pass(dc)
    assert f.accepts(home) and f.accepts(unknown)  # unbekannt wird nicht aussortiert
    ProviderLookup(None).annotate(unknown)  # ohne Datenbank passiert einfach nichts


def test_no_datacenter_option_roundtrip():
    opts = RunOptions.from_args(parse_args(["--no-datacenter", "--want", "5"]))
    assert opts.filters.no_datacenter and "ohne Rechenzentren" in opts.filters.describe()
    assert RunOptions.from_args(parse_args(opts.to_argv())) == opts



def test_non_string_providers_invalidate_the_file(tmp_path):
    import json
    import struct
    db = AsnDB.from_csv(CSV, "2026-09")
    db.orgs = [123 for _ in db.orgs]  # kaputte Tabelle mit Zahlen statt Namen
    table = json.dumps(db.orgs).encode()
    with (tmp_path / "asn.bin").open("wb") as fh:
        fh.write(b"PSASN1" + b"2026-09" + struct.pack("!II", len(db), len(table)))
        for arr in (db.starts, db.ends, db.asns, db.org_index):
            arr.tofile(fh)
        fh.write(table)
    assert AsnDB.load(tmp_path / "asn.bin") is None


def test_slow_provider_download_does_not_break_the_run(monkeypatch, tmp_path):
    """Erster Lauf ohne ASN-Datei: der Download läuft noch, wenn die Prüfung fertig ist – der Lauf muss trotzdem
    sauber zu Ende gehen und die Anbieter nachtragen."""
    from proxyscraper import app
    from proxyscraper import output as out_mod

    async def slow_load():
        await asyncio.sleep(0.2)
        return AsnDB.from_csv(CSV, "2026-09")

    async def fake_run_checks(jobs, checker, opts, dashboard, writer, geo, **kw):
        from proxyscraper.pipeline import CheckRun
        run = CheckRun()
        r = CheckResult("http 1.2.3.4:80", "http", "1.2.3.4:80", 100, "8.8.8.8", https=True, anonymity="elite")
        run.results.append(r)
        run.working.add(r.key)
        run.checked.append(r.key)
        return run

    monkeypatch.setattr(app.AsnDB, "load", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(app, "load_asn_db", slow_load)
    monkeypatch.setattr(app, "run_checks", fake_run_checks)
    monkeypatch.setattr(out_mod, "RESULTS_DIR", tmp_path)
    monkeypatch.setattr(app.Run, "learn", lambda self, run, blocked: {})
    run = app.Run(RunOptions(no_geo=True), show_banner=False)
    run.judges = [__import__("proxyscraper.judges", fromlist=["x"]).JudgeProbe(
        __import__("proxyscraper.judges", fromlist=["x"]).Judge("a"), "1.1.1.1", 1)]
    asyncio.run(run.check_and_report(["http 1.2.3.4:80"]))
    import json
    rows = json.loads((out_mod.latest_run_dir(tmp_path) / "proxies.json").read_text())
    assert rows[0]["org"] == "Google LLC" and rows[0]["hosting"] is True
