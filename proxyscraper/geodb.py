"""Countries offline – with the free country database from DB-IP (DB-IP Lite, CC BY 4.0).

The CSV (≈ 4.5 MB gzip, new every month) is loaded once a month and turned into two number arrays
plus country codes; a lookup is then a binary search and takes microseconds. That way the tool no
longer depends on ip-api.com (15 requests/minute) – that's only a fallback for IPs missing here,
or when the database can't be loaded.

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
HEADER = len(MAGIC) + 7 + 4  # magic, month, count


def _ip_to_int(ip: str) -> int:
    return struct.unpack("!I", socket.inet_aton(ip))[0]


class CountryDB:
    def __init__(self, starts: array, ends: array, codes: bytes, month: str):
        self.starts = starts
        self.ends = ends
        self.codes = codes  # 2 bytes per range
        self.month = month

    def __len__(self) -> int:
        return len(self.starts)

    def lookup(self, ip: str) -> str:
        """'8.8.8.8' -> 'US'; '' if unknown or not a country (ZZ = reserved)."""
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
        """DB-IP CSV ("start,end,country" for IPv4 and IPv6) -> only the IPv4 ranges."""
        starts, ends, codes = array("I"), array("I"), bytearray()
        for line in io.StringIO(text):
            fields = line.rstrip("\r\n").split(",")
            if len(fields) < 3 or ":" in fields[0]:
                continue  # IPv6 or a broken line
            start, end, code = fields[0], fields[1], fields[2].strip()  # evtl. weitere Spalten ignorieren
            if len(code) != 2 or not (code.isascii() and code.isalpha()):
                continue
            try:
                s, e = _ip_to_int(start), _ip_to_int(end)
            except OSError:
                continue  # broken address – skip just this line
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
            size = path.stat().st_size
            with path.open("rb") as fh:
                if fh.read(len(MAGIC)) != MAGIC:
                    return None
                month = fh.read(7).decode("ascii").strip()
                (count,) = struct.unpack("!I", fh.read(4))
                if size != HEADER + count * 10:  # 2 × 4 bytes + 2 bytes of country per range
                    return None  # truncated or broken – don't blindly allocate memory
                starts, ends = array("I"), array("I")
                starts.fromfile(fh, count)
                ends.fromfile(fh, count)
                codes = fh.read(2 * count)
        except (OSError, EOFError, ValueError, struct.error, UnicodeDecodeError):
            return None
        if len(codes) != 2 * count or not (codes.isascii() and codes.isalpha()):
            return None  # broken country codes would only show up during a lookup
        return cls(starts, ends, codes, month)


def _months(today: date):
    """Current and previous month as 'YYYY-MM' – at the start of a month the new file may not be there yet."""
    yield today.strftime("%Y-%m")
    prev = date(today.year - (today.month == 1), 12 if today.month == 1 else today.month - 1, 1)
    yield prev.strftime("%Y-%m")


def is_current(db: Optional[CountryDB], today: Optional[date] = None) -> bool:
    return db is not None and db.month == (today or date.today()).strftime("%Y-%m")


async def load_country_db(path: Path = DB_FILE, today: Optional[date] = None, fetch=http_get) -> Optional[CountryDB]:
    """Database from data/ – new from DB-IP once a month. None if there is none at all.

    May download (up to two attempts of 30 s each) – so call it in the background."""
    today = today or date.today()
    current = CountryDB.load(path)
    if current and current.month == today.strftime("%Y-%m"):
        return current
    for month in _months(today):
        if current and current.month >= month:
            return current  # there's no newer one (yet)
        try:
            data = await fetch(URL.format(month=month), timeout=30)
            db = CountryDB.from_csv(gzip.decompress(data).decode("ascii", "replace"), month)
        except Exception:  # unreachable or broken – try the next month or keep the old file
            continue
        if len(db) > 1000:  # plausibility: the real file has more than 100,000 ranges
            db.save(path)
            return db
    return current
