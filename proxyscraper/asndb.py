"""Anbieter (ASN) der Exit-IPs offline – mit der freien ASN-Datenbank von DB-IP (DB-IP Lite, CC BY 4.0).

Wie geodb.py: einmal im Monat laden (≈ 7 MB gzip, ~400.000 IPv4-Bereiche), in Arrays umwandeln,
Lookup per Binärsuche. Dazu eine Einschätzung, ob der Anbieter ein Rechenzentrum/Hoster ist –
Proxys mit Exit in Rechenzentren werden von vielen Seiten schneller gesperrt als solche bei
Heim- oder Mobilfunkanschlüssen.

Die Einschätzung ist eine Heuristik über den Anbieternamen (Cloud, Hosting, bekannte Hoster), keine
Gewissheit. Gemessen an 316 funktionierenden Proxys lagen so ~45 % in Rechenzentren.

IP Geolocation by DB-IP: https://db-ip.com
"""

from __future__ import annotations

import csv
import gzip
import io
import json
import re
import socket
import struct
from array import array
from bisect import bisect_right
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import List, Optional

from .geodb import _months
from .netio import http_get
from .paths import DATA_DIR

DB_FILE = DATA_DIR / "geo" / "dbip-asn-ipv4.bin"
URL = "https://download.db-ip.com/free/dbip-asn-lite-{month}.csv.gz"
MAGIC = b"PSASN1"

HOSTING_RE = re.compile(
    r"host|cloud|data ?cent|server|\bvps\b|colo|amazon|\baws\b|google|microsoft|azure|"
    r"digitalocean|ovh|hetzner|linode|akamai|vultr|choopa|contabo|leaseweb|m247|alibaba|tencent|oracle|"
    r"scaleway|ionos|godaddy|fastly|cloudflare|datacamp|cdn77|psychz|colocrossing|quadranet|hostwinds|"
    r"kamatera|upcloud|netcup|strato|hosteurope|constant company|g-core|gcore|stark industries|aeza|"
    r"pq hosting|serverius|worldstream|zenlayer|ucloud|huawei|baidu|kingsoft|performive|nocix|datasource|"
    r"frantech|buyvm|ramnode|namecheap|dreamhost|packet|equinix|dataforest|servinga|hydra communications",
    re.IGNORECASE,
)


def is_hosting(org: str) -> bool:
    return bool(HOSTING_RE.search(org or ""))


def _ip_to_int(ip: str) -> int:
    return struct.unpack("!I", socket.inet_aton(ip))[0]


@dataclass(frozen=True)
class Provider:
    asn: int
    org: str
    hosting: bool


class AsnDB:
    def __init__(self, starts: array, ends: array, asns: array, org_index: array, orgs: List[str], month: str):
        self.starts, self.ends, self.asns, self.org_index = starts, ends, asns, org_index
        self.orgs = orgs
        self.hosting = [is_hosting(o) for o in orgs]
        self.month = month

    def __len__(self) -> int:
        return len(self.starts)

    def lookup(self, ip: str) -> Optional[Provider]:
        try:
            n = _ip_to_int(ip)
        except OSError:
            return None
        i = bisect_right(self.starts, n) - 1
        if i < 0 or n > self.ends[i]:
            return None
        k = self.org_index[i]
        return Provider(self.asns[i], self.orgs[k], self.hosting[k])

    @classmethod
    def from_csv(cls, text: str, month: str) -> "AsnDB":
        """DB-IP-CSV ("start,end,asn,\\"Anbieter\\"") -> nur IPv4. Anbieternamen werden nur einmal gespeichert."""
        starts, ends, asns, org_index = array("I"), array("I"), array("I"), array("I")
        orgs: List[str] = []
        seen = {}
        for row in csv.reader(io.StringIO(text)):
            if len(row) < 4 or ":" in row[0] or not row[2].isdigit():
                continue
            try:
                s, e = _ip_to_int(row[0]), _ip_to_int(row[1])
            except OSError:
                continue
            org = row[3].strip()
            k = seen.get(org)
            if k is None:
                k = seen[org] = len(orgs)
                orgs.append(org)
            starts.append(s)
            ends.append(e)
            asns.append(int(row[2]))
            org_index.append(k)
        return cls(starts, ends, asns, org_index, orgs, month)

    def save(self, path: Path = DB_FILE) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        table = json.dumps(self.orgs, ensure_ascii=False).encode("utf-8")
        tmp = path.with_suffix(".tmp")
        with tmp.open("wb") as fh:
            fh.write(MAGIC + self.month.encode("ascii").ljust(7) + struct.pack("!II", len(self.starts), len(table)))
            for arr in (self.starts, self.ends, self.asns, self.org_index):
                arr.tofile(fh)
            fh.write(table)
        tmp.replace(path)

    @classmethod
    def load(cls, path: Path = DB_FILE) -> Optional["AsnDB"]:
        try:
            size = path.stat().st_size
            with path.open("rb") as fh:
                if fh.read(len(MAGIC)) != MAGIC:
                    return None
                month = fh.read(7).decode("ascii").strip()
                count, table_len = struct.unpack("!II", fh.read(8))
                if size != len(MAGIC) + 7 + 8 + count * 16 + table_len:
                    return None  # abgeschnitten oder kaputt – nicht blind Speicher reservieren
                arrays = []
                for _ in range(4):
                    arr = array("I")
                    arr.fromfile(fh, count)
                    arrays.append(arr)
                orgs = json.loads(fh.read(table_len).decode("utf-8"))
        except (OSError, EOFError, ValueError, struct.error, UnicodeDecodeError):
            return None
        if not isinstance(orgs, list) or not all(isinstance(o, str) for o in orgs) \
                or any(k >= len(orgs) for k in arrays[3]):
            return None
        return cls(*arrays, orgs, month)


def is_current(db: Optional[AsnDB], today: Optional[date] = None) -> bool:
    return db is not None and db.month == (today or date.today()).strftime("%Y-%m")


async def load_asn_db(path: Path = DB_FILE, today: Optional[date] = None, fetch=http_get) -> Optional[AsnDB]:
    """Datenbank aus data/ – einmal im Monat neu von DB-IP. Lädt ggf. herunter, deshalb im Hintergrund aufrufen."""
    today = today or date.today()
    current = AsnDB.load(path)
    if is_current(current, today):
        return current
    for month in _months(today):
        if current and current.month >= month:
            return current
        try:
            data = await fetch(URL.format(month=month), timeout=30)
            db = AsnDB.from_csv(gzip.decompress(data).decode("utf-8", "replace"), month)
        except Exception:  # nicht erreichbar oder kaputt – nächsten Monat versuchen bzw. alte Datei nehmen
            continue
        if len(db) > 1000:
            db.save(path)
            return db
    return current


class ProviderLookup:
    """Hält die (evtl. erst später geladene) Datenbank und trägt Anbieter in Treffer ein."""

    def __init__(self, db: Optional[AsnDB] = None):
        self.db = db

    def annotate(self, r) -> None:
        provider = self.db.lookup(r.exit_ip) if self.db else None
        if provider:
            r.asn, r.org, r.hosting = provider.asn, provider.org, provider.hosting

    def __bool__(self) -> bool:
        return True
