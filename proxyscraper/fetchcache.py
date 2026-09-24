"""Unveränderte Listen nicht jedes Mal neu laden.

Pro Liste merkt sich der Cache ETag bzw. Last-Modified und die geparsten Proxy-Schlüssel.
Beim nächsten Lauf fragt der Download mit If-None-Match / If-Modified-Since; kommt 304 zurück,
stammen die Schlüssel aus dem Cache. Gespeichert wird ungefiltert (alle Typen), weil sich
--types zwischen zwei Läufen ändern kann.

  data/fetch-cache/index.json      url -> {etag, modified, type, file, used}
  data/fetch-cache/<sha1>.txt.gz   die Schlüssel, einer pro Zeile
"""

from __future__ import annotations

import gzip
import hashlib
import json
import time
import zlib
from pathlib import Path
from typing import Dict, Optional

from .paths import DATA_DIR, atomic_write

CACHE_DIR = DATA_DIR / "fetch-cache"
FORGET_AFTER = 14 * 86400  # Listen, die so lange nicht mehr geladen wurden, fliegen raus


def _valid_entry(entry) -> bool:
    return (isinstance(entry, dict) and isinstance(entry.get("file"), str) and entry["file"].endswith(".txt.gz")
            and "/" not in entry["file"] and "\\" not in entry["file"]
            and isinstance(entry.get("etag", ""), str) and isinstance(entry.get("modified", ""), str)
            and isinstance(entry.get("used", 0), (int, float)))


class FetchCache:
    def __init__(self, directory: Path = CACHE_DIR, enabled: bool = True):
        self.dir = directory
        self.enabled = enabled
        self.entries: Dict[str, dict] = {}
        self.hits = 0
        if enabled:
            try:
                raw = json.loads((directory / "index.json").read_text(encoding="utf-8"))
            except (OSError, ValueError):
                raw = {}
            # nur Einträge mit der erwarteten Form – eine kaputte index.json heißt einfach "leerer Cache"
            if isinstance(raw, dict):
                self.entries = {url: e for url, e in raw.items() if _valid_entry(e)}

    def conditional_headers(self, url: str, ptype: str) -> Dict[str, str]:
        """Header für eine bedingte Anfrage – leer, wenn nichts (Brauchbares) im Cache liegt.

        ptype ist der Typ, mit dem die Liste geparst wird: Ändert er sich (z. B. http -> auto),
        passen die gespeicherten Schlüssel nicht mehr und die Liste wird neu geladen."""
        entry = self.entries.get(url) if self.enabled else None
        if not entry or entry.get("type") != ptype or not (self.dir / entry["file"]).is_file():
            return {}
        headers = {}
        if entry.get("etag"):
            headers["If-None-Match"] = entry["etag"]
        if entry.get("modified"):
            headers["If-Modified-Since"] = entry["modified"]
        return headers

    def load(self, url: str) -> Optional[str]:
        """Schlüssel aus dem Cache nach einer 304-Antwort (None, wenn die Datei kaputt ist)."""
        entry = self.entries.get(url)
        if not entry:
            return None
        try:
            keys = gzip.decompress((self.dir / entry["file"]).read_bytes()).decode("utf-8")
        except (OSError, EOFError, UnicodeDecodeError, zlib.error):  # kaputte Datei = Cache-Miss
            return None
        entry["used"] = time.time()
        self.hits += 1
        return keys

    def store(self, url: str, headers: Dict[bytes, bytes], keys: str, ptype: str) -> None:
        """Nach einem normalen Download: merken, falls der Server ETag oder Last-Modified liefert."""
        if not self.enabled:
            return
        etag = headers.get(b"etag", b"").decode("latin-1").strip()
        modified = headers.get(b"last-modified", b"").decode("latin-1").strip()
        if not etag and not modified:
            old = self.entries.pop(url, None)
            if old:  # Datei gleich mit entfernen, sonst bliebe sie für immer liegen
                (self.dir / old["file"]).unlink(missing_ok=True)
            return
        name = hashlib.sha1(url.encode()).hexdigest() + ".txt.gz"
        self.dir.mkdir(parents=True, exist_ok=True)
        tmp = self.dir / (name + ".tmp")
        tmp.write_bytes(gzip.compress(keys.encode("utf-8"), compresslevel=5))
        tmp.replace(self.dir / name)
        self.entries[url] = {"etag": etag, "modified": modified, "type": ptype, "file": name, "used": time.time()}

    def save(self, now: Optional[float] = None) -> None:
        index = self.dir / "index.json"
        if not self.enabled or (not self.entries and not index.exists()):
            return  # auch ein leerer Index wird geschrieben – sonst käme ein entfernter Eintrag zurück
        now = time.time() if now is None else now
        for url in [u for u, e in self.entries.items() if now - e.get("used", 0) > FORGET_AFTER]:
            (self.dir / self.entries.pop(url)["file"]).unlink(missing_ok=True)
        atomic_write(index, json.dumps(self.entries, indent=0, sort_keys=True))
