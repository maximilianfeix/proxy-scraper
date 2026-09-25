"""Don't reload unchanged lists every time.

For every list the cache remembers the ETag or Last-Modified and the parsed proxy keys.
On the next run the download asks with If-None-Match / If-Modified-Since; if 304 comes back,
the keys come from the cache. They are stored unfiltered (all types), because --types can
change between two runs.

  data/fetch-cache/index.json      url -> {etag, modified, type, file, used}
  data/fetch-cache/<sha1>.txt.gz   the keys, one per line
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
FORGET_AFTER = 14 * 86400  # lists that haven't been loaded for this long are dropped


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
            # only entries of the expected shape – a broken index.json simply means "empty cache"
            if isinstance(raw, dict):
                self.entries = {url: e for url, e in raw.items() if _valid_entry(e)}

    def conditional_headers(self, url: str, ptype: str) -> Dict[str, str]:
        """Headers for a conditional request – empty if there's nothing (usable) in the cache.

        ptype is the type the list is parsed with: if it changes (e.g. http -> auto),
        the stored keys no longer fit and the list is loaded again."""
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
        """Keys from the cache after a 304 response (None if the file is broken)."""
        entry = self.entries.get(url)
        if not entry:
            return None
        try:
            keys = gzip.decompress((self.dir / entry["file"]).read_bytes()).decode("utf-8")
        except (OSError, EOFError, UnicodeDecodeError, zlib.error):  # broken file = cache miss
            return None
        entry["used"] = time.time()
        self.hits += 1
        return keys

    def store(self, url: str, headers: Dict[bytes, bytes], keys: str, ptype: str) -> None:
        """After a normal download: remember it if the server sends an ETag or Last-Modified."""
        if not self.enabled:
            return
        etag = headers.get(b"etag", b"").decode("latin-1").strip()
        modified = headers.get(b"last-modified", b"").decode("latin-1").strip()
        if not etag and not modified:
            old = self.entries.pop(url, None)
            if old:  # remove the file too, otherwise it would stay forever
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
            return  # an empty index is written too – otherwise a removed entry would come back
        now = time.time() if now is None else now
        for url in [u for u, e in self.entries.items() if now - e.get("used", 0) > FORGET_AFTER]:
            (self.dir / self.entries.pop(url)["file"]).unlink(missing_ok=True)
        atomic_write(index, json.dumps(self.entries, indent=0, sort_keys=True))
