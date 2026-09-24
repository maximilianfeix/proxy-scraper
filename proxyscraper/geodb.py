"""Länder offline bestimmen – mit der freien Länder-Datenbank von DB-IP (DB-IP Lite, CC BY 4.0).

Die CSV (≈ 4,5 MB gzip, monatlich neu) wird einmal im Monat geladen und in zwei Zahlen-Arrays plus
Ländercodes umgewandelt; ein Lookup ist dann eine Binärsuche und dauert Mikrosekunden. Damit hängt
das Tool nicht mehr an ip-api.com (15 Anfragen/Minute) – das bleibt nur noch Reserve für IPs, die
hier fehlen, oder wenn die Datenbank nicht geladen werden kann.

IP Geolocation by DB-IP: https://db-ip.com
"""

from __future__ import annotations

import gzip
import io
import socket
import struct
from array import array
from bisect import bisect_right
from datetime import date
from pathlib import Path
from typing import Optional

from .netio import http_get
from .paths import DATA_DIR

DB_FILE = DATA_DIR / "geo" / "dbip-country-ipv4.bin"
URL = "https://download.db-ip.com/free/dbip-country-lite-{month}.csv.gz"
MAGIC = b"PSGEO1"


def _ip_to_int(ip: str) -> int:
    return struct.unpack("!I", socket.inet_aton(ip))[0]


class CountryDB:
    def __init__(self, starts: array, ends: array, codes: bytes, month: str):
        self.starts = starts
        self.ends = ends
        self.codes = codes  # 2 Bytes pro Bereich
        self.month = month

    def __len__(self) -> int:
        return len(self.starts)

    def lookup(self, ip: str) -> str:
        """'8.8.8.8' -> 'US'; '' wenn unbekannt oder kein Land (ZZ = reserviert)."""
        try:
            n = _ip_to_int(ip)
        except OSError:
            return ""
        i = bisect_right(self.starts, n) - 1
        if i < 0 or n > self.ends[i]:
            return ""
        code = self.codes[2 * i:2 * i + 2].decode("ascii")
        return "" if code == "ZZ" else code

    @classmethod
    def from_csv(cls, text: str, month: str) -> "CountryDB":
        """DB-IP-CSV ("start,end,land" für IPv4 und IPv6) -> nur die IPv4-Bereiche."""
        starts, ends, codes = array("I"), array("I"), bytearray()
        for line in io.StringIO(text):
            start, _, rest = line.partition(",")
            if ":" in start or not rest:
                continue  # IPv6 oder kaputte Zeile
            end, _, code = rest.partition(",")
            code = code.strip()
            if len(code) != 2:
                continue
            s, e = _ip_to_int(start), _ip_to_int(end)
            if codes and codes[-2:] == code.encode() and s == ends[-1] + 1:
                ends[-1] = e  # Nachbarbereich desselben Landes zusammenfassen
                continue
            starts.append(s)
            ends.append(e)
            codes += code.encode("ascii")
        return cls(starts, ends, bytes(codes), month)

    def save(self, path: Path = DB_FILE) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        with tmp.open("wb") as fh:
            fh.write(MAGIC + self.month.encode("ascii").ljust(7) + struct.pack("!I", len(self.starts)))
            self.starts.tofile(fh)
            self.ends.tofile(fh)
            fh.write(self.codes)
        tmp.replace(path)

    @classmethod
    def load(cls, path: Path = DB_FILE) -> Optional["CountryDB"]:
        try:
            with path.open("rb") as fh:
                if fh.read(len(MAGIC)) != MAGIC:
                    return None
                month = fh.read(7).decode("ascii").strip()
                (count,) = struct.unpack("!I", fh.read(4))
                starts, ends = array("I"), array("I")
                starts.fromfile(fh, count)
                ends.fromfile(fh, count)
                codes = fh.read(2 * count)
        except (OSError, EOFError, ValueError, struct.error, UnicodeDecodeError):
            return None
        if len(codes) != 2 * count:
            return None
        return cls(starts, ends, codes, month)


def _months(today: date):
    """Aktueller und vorheriger Monat als 'JJJJ-MM' – Anfang des Monats ist die neue Datei evtl. noch nicht da."""
    yield today.strftime("%Y-%m")
    prev = date(today.year - (today.month == 1), 12 if today.month == 1 else today.month - 1, 1)
    yield prev.strftime("%Y-%m")


async def load_country_db(path: Path = DB_FILE, today: Optional[date] = None, fetch=http_get) -> Optional[CountryDB]:
    """Datenbank aus data/ – einmal im Monat neu von DB-IP. None, wenn es gar keine gibt."""
    today = today or date.today()
    current = CountryDB.load(path)
    if current and current.month == today.strftime("%Y-%m"):
        return current
    for month in _months(today):
        if current and current.month >= month:
            return current  # neuere gibt es (noch) nicht
        try:
            data = await fetch(URL.format(month=month), timeout=60)
            db = CountryDB.from_csv(gzip.decompress(data).decode("ascii", "replace"), month)
        except Exception:  # nicht erreichbar oder kaputt – nächsten Monat versuchen bzw. alte Datei nehmen
            continue
        if len(db) > 1000:  # Plausibilität: die echte Datei hat über 100.000 Bereiche
            db.save(path)
            return db
    return current
