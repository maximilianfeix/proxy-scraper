"""Offline-Länder: DB-IP-CSV einlesen, speichern, monatlich erneuern, Rückfall auf ip-api."""

import asyncio
import gzip
from datetime import date

from proxyscraper.geo import GeoResolver
from proxyscraper.geodb import CountryDB, load_country_db

CSV = """0.0.0.0,0.255.255.255,ZZ
1.0.0.0,1.0.0.255,AU
1.0.1.0,1.0.3.255,CN
1.0.4.0,1.0.7.255,CN
8.8.8.0,8.8.8.255,US
2001:db8::,2001:db8::ffff,DE
kaputt
"""


def big_csv(n=2000):
    """Genug Bereiche, um die Plausibilitätsprüfung (> 1000) zu bestehen."""
    return "\n".join(f"10.{i // 256}.{i % 256}.0,10.{i // 256}.{i % 256}.127,{'DE' if i % 2 else 'AT'}"
                     for i in range(n)) + "\n"


def test_parse_lookup_and_merge():
    db = CountryDB.from_csv(CSV, "2026-09")
    assert len(db) == 4  # IPv6 und kaputte Zeile raus, die zwei CN-Nachbarn zusammengefasst
    assert db.lookup("1.0.0.1") == "AU"
    assert db.lookup("1.0.5.5") == "CN" and db.lookup("1.0.2.2") == "CN"
    assert db.lookup("8.8.8.8") == "US"
    assert db.lookup("0.1.2.3") == ""       # ZZ = reserviert
    assert db.lookup("5.5.5.5") == ""       # Lücke
    assert db.lookup("kein.ip") == ""


def test_save_and_load_roundtrip(tmp_path):
    db = CountryDB.from_csv(CSV, "2026-09")
    db.save(tmp_path / "geo.bin")
    again = CountryDB.load(tmp_path / "geo.bin")
    assert again.month == "2026-09" and again.lookup("8.8.8.8") == "US" and len(again) == len(db)


def test_broken_file_is_ignored(tmp_path):
    (tmp_path / "geo.bin").write_bytes(b"PSGEO1" + b"2026-09" + b"\xff\xff\xff\xff")
    assert CountryDB.load(tmp_path / "geo.bin") is None
    assert CountryDB.load(tmp_path / "fehlt.bin") is None


class Fetch:
    def __init__(self, available):
        self.available = available  # Monat -> CSV
        self.urls = []

    async def __call__(self, url, timeout):
        self.urls.append(url)
        for month, csv in self.available.items():
            if month in url:
                return gzip.compress(csv.encode())
        raise ConnectionError("404")


def test_current_file_is_used_without_download(tmp_path):
    CountryDB.from_csv(big_csv(), "2026-09").save(tmp_path / "geo.bin")
    fetch = Fetch({})
    db = asyncio.run(load_country_db(tmp_path / "geo.bin", date(2026, 9, 25), fetch))
    assert db.month == "2026-09" and fetch.urls == []


def test_new_month_is_downloaded(tmp_path):
    CountryDB.from_csv(big_csv(), "2026-08").save(tmp_path / "geo.bin")
    fetch = Fetch({"2026-09": big_csv()})
    db = asyncio.run(load_country_db(tmp_path / "geo.bin", date(2026, 9, 25), fetch))
    assert db.month == "2026-09" and CountryDB.load(tmp_path / "geo.bin").month == "2026-09"


def test_early_in_the_month_the_previous_file_is_fine(tmp_path):
    fetch = Fetch({"2026-08": big_csv()})  # September noch nicht veröffentlicht
    db = asyncio.run(load_country_db(tmp_path / "geo.bin", date(2026, 9, 1), fetch))
    assert db.month == "2026-08"


def test_offline_keeps_the_old_file(tmp_path):
    CountryDB.from_csv(big_csv(), "2026-07").save(tmp_path / "geo.bin")
    db = asyncio.run(load_country_db(tmp_path / "geo.bin", date(2026, 9, 25), Fetch({})))
    assert db.month == "2026-07"
    assert asyncio.run(load_country_db(tmp_path / "leer.bin", date(2026, 9, 25), Fetch({}))) is None


def test_implausibly_small_download_is_rejected(tmp_path):
    db = asyncio.run(load_country_db(tmp_path / "geo.bin", date(2026, 9, 25), Fetch({"2026-09": CSV})))
    assert db is None and not (tmp_path / "geo.bin").exists()


def test_resolver_asks_offline_first_then_falls_back_to_the_api():
    async def make():  # GeoResolver legt ein asyncio.Event an – unter Python 3.9 nur in einer Loop
        return GeoResolver(offline=CountryDB.from_csv(CSV, "2026-09"))

    resolver = asyncio.run(make())
    resolver.cache = {}
    assert resolver.request("8.8.8.8") == "US" and resolver.pending == []
    assert resolver.request("5.5.5.5") == "" and resolver.pending == ["5.5.5.5"]  # nicht in der Datenbank
    assert resolver.offline_hits == 1


def test_huge_count_in_a_broken_file_does_not_allocate(tmp_path):
    import struct
    (tmp_path / "geo.bin").write_bytes(b"PSGEO1" + b"2026-09" + struct.pack("!I", 0xFFFFFFFF) + b"\0" * 20)
    assert CountryDB.load(tmp_path / "geo.bin") is None


def test_one_bad_row_does_not_throw_away_the_database():
    db = CountryDB.from_csv(CSV + "1.2.3.999,1.2.4.0,DE\n9.9.9.0,9.9.9.255,CH\n", "2026-09")
    assert db.lookup("9.9.9.9") == "CH" and db.lookup("8.8.8.8") == "US"


def test_background_refresh_switches_the_resolver_to_offline(monkeypatch):
    from proxyscraper import app

    async def fake_load():
        return CountryDB.from_csv(CSV, "2026-09")

    monkeypatch.setattr(app, "load_country_db", fake_load)

    async def go():
        resolver = GeoResolver()
        await app.Run.refresh_country_db(resolver)
        return resolver

    resolver = asyncio.run(go())
    assert resolver.offline is not None and resolver.offline.lookup("8.8.8.8") == "US"


def test_is_current():
    from proxyscraper.geodb import is_current
    db = CountryDB.from_csv(CSV, "2026-09")
    assert is_current(db, date(2026, 9, 25)) and not is_current(db, date(2026, 10, 1)) and not is_current(None)


def test_extra_columns_and_odd_codes_are_handled():
    csv = "1.0.0.0,1.0.0.255,AU,Australia\n1.0.1.0,1.0.1.255,Ä1\n8.8.8.0,8.8.8.255,US\n"
    db = CountryDB.from_csv(csv, "2026-09")
    assert db.lookup("1.0.0.1") == "AU" and db.lookup("1.0.1.1") == "" and db.lookup("8.8.8.8") == "US"


def test_switching_to_offline_resolves_waiting_ips_consistently():
    async def go():
        resolved = {}
        resolver = GeoResolver(on_resolved=lambda ip, cc: resolved.setdefault(ip, cc))
        resolver.cache = {}
        resolver.request("8.8.8.8")   # noch keine Datenbank -> wartet auf ip-api
        resolver.request("5.5.5.5")
        resolver.use_offline(CountryDB.from_csv(CSV, "2026-09"))
        return resolver, resolved

    resolver, resolved = asyncio.run(go())
    assert resolved == {"8.8.8.8": "US"}           # sofort aus der Datenbank gemeldet
    assert resolver.pending == ["5.5.5.5"]          # nur was die Datenbank nicht kennt, bleibt für ip-api


def test_one_country_per_exit_ip_even_when_sources_disagree():
    async def go():
        resolver = GeoResolver()
        resolver.cache = {}
        first = resolver.request("8.8.8.8")          # noch keine Datenbank -> ip-api
        resolver.cache["8.8.8.8"] = ["NL", 9e9]       # ip-api sagt NL ...
        resolver._assign("8.8.8.8", "NL")
        resolver.use_offline(CountryDB.from_csv(CSV, "2026-09"))  # ... die Datenbank sagt US
        return first, resolver.request("8.8.8.8")

    first, later = asyncio.run(go())
    assert first == "" and later == "NL"  # innerhalb des Laufs bleibt es bei der ersten Einordnung


def test_non_letter_country_codes_invalidate_the_file(tmp_path):
    db = CountryDB.from_csv(CSV, "2026-09")
    db.save(tmp_path / "geo.bin")
    data = bytearray((tmp_path / "geo.bin").read_bytes())
    data[-1] = 0xFF  # letzter Ländercode kaputt, Größe unverändert
    (tmp_path / "geo.bin").write_bytes(bytes(data))
    assert CountryDB.load(tmp_path / "geo.bin") is None
