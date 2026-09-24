"""
Quellenverwaltung für den Proxy-Scraper:

- lädt die kuratierte Quellenliste (sources.json) und per --discover gefundene Quellen,
- löst Meta-Quellen auf (fremd gepflegte Listen von Quell-URLs),
- findet neue Proxy-Listen auf GitHub,
- merkt sich pro Quelle, wie viele ihrer Proxys wirklich funktionieren, und
  überspringt tote, veraltete oder unerreichbare Quellen.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import subprocess
import time
import warnings
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Awaitable, Callable, Dict, Iterable, List, Optional, Tuple
from urllib.parse import quote, urlencode

from .parsing import PROXY_TYPES, TYPE_ALIASES
from .paths import DATA_DIR, PROJECT_DIR, atomic_write

SOURCES_FILE = PROJECT_DIR / "sources.json"
DISCOVERED_FILE = DATA_DIR / "sources_discovered.json"
STATS_FILE = DATA_DIR / "source_stats.json"

GH_RAW = "https://raw.githubusercontent.com"
# "auto" = Liste enthält typ://ip:port-Zeilen, der Typ steht pro Zeile
SOURCE_TYPES = PROXY_TYPES + ("auto",)

# url -> Typ
SourceMap = Dict[str, str]
Getter = Callable[..., Awaitable[bytes]]


# --------------------------------------------------------------------------- #
# URLs & Quellenlisten
# --------------------------------------------------------------------------- #

_GH_BLOB_RE = re.compile(r"^https://github\.com/([^/]+)/([^/]+)/(?:raw|blob)/(?:refs/heads/)?(.+)$")


def normalize_url(url: str) -> Optional[str]:
    """Vereinheitlicht Quell-URLs, damit dieselbe Datei nicht mehrfach geladen wird.

    github.com/…/raw/… -> raw.githubusercontent.com/…, '/refs/heads/' entfällt,
    Format-Anhänge wie ',,ColonURL' werden abgeschnitten. Vorlagen mit {…} -> None.
    """
    url = url.strip().split(",", 1)[0].strip()
    if not url.startswith(("http://", "https://")) or "{" in url:
        return None
    m = _GH_BLOB_RE.match(url)
    if m:
        url = f"{GH_RAW}/{m[1]}/{m[2]}/{m[3]}"
    if url.startswith(GH_RAW):
        url = url.replace("/refs/heads/", "/", 1)
    return url


def _add(target: SourceMap, url: str, ptype: str) -> None:
    ptype = TYPE_ALIASES.get(ptype.lower(), "")
    url = normalize_url(url) if url else None
    if url and ptype:
        target.setdefault(url, ptype)


def load_source_file(path: Path = SOURCES_FILE) -> Tuple[SourceMap, List[dict]]:
    """Liest sources.json -> (Quellen, Meta-Quellen)."""
    data = json.loads(path.read_text(encoding="utf-8"))
    sources: SourceMap = {}
    for ptype, urls in data.get("sources", {}).items():
        for url in urls:
            _add(sources, url, ptype)
    return sources, list(data.get("meta", []))


def load_discovered(path: Path = DISCOVERED_FILE) -> SourceMap:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    out: SourceMap = {}
    for url, ptype in data.get("sources", {}).items():
        _add(out, url, ptype)
    return out


def discovered_age_days(path: Path = DISCOVERED_FILE) -> Optional[float]:
    """Alter der letzten Discovery in Tagen, None wenn es noch keine gab."""
    try:
        generated = json.loads(path.read_text(encoding="utf-8"))["generated"]
        return (datetime.now(timezone.utc) - datetime.fromisoformat(generated)).total_seconds() / DAY
    except (OSError, ValueError, KeyError, TypeError):
        return None


def save_discovered(sources: SourceMap, path: Path = DISCOVERED_FILE) -> None:
    payload = {"generated": datetime.now(timezone.utc).isoformat(timespec="seconds"), "sources": sources}
    atomic_write(path, json.dumps(payload, indent=1, sort_keys=True))


# --------------------------------------------------------------------------- #
# Meta-Quellen: fremd gepflegte Listen von Quell-URLs
# --------------------------------------------------------------------------- #

def parse_url_list(data: bytes, ptype: str) -> SourceMap:
    """Eine Quell-URL pro Zeile (z. B. gfpcom/free-proxy-list/sources/http.txt)."""
    out: SourceMap = {}
    for line in data.decode("utf-8", "ignore").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            _add(out, line, ptype)
    return out


_TOML_SECTION_RE = re.compile(r"^\s*\[scraping\.(\w+)\]")
_TOML_URL_RE = re.compile(r'"(https?://[^"]+)"')


def parse_monosans_toml(data: bytes) -> SourceMap:
    """URLs aus den [scraping.<typ>]-Abschnitten der config.toml von monosans/proxy-scraper-checker.

    Python 3.9 hat kein tomllib – für diese flache Struktur reicht ein Zeilen-Parser.
    """
    out: SourceMap = {}
    section = None
    for line in data.decode("utf-8", "ignore").splitlines():
        m = _TOML_SECTION_RE.match(line)
        if m:
            section = m[1]
            continue
        if line.lstrip().startswith("["):
            section = None
        elif section in PROXY_TYPES and not line.lstrip().startswith("#"):
            for url in _TOML_URL_RE.findall(line):
                _add(out, url, section)
    return out


META_PARSERS: Dict[str, Callable[[bytes, dict], SourceMap]] = {
    "url-list": lambda data, meta: parse_url_list(data, meta.get("type", "auto")),
    "monosans-toml": lambda data, meta: parse_monosans_toml(data),
}


async def resolve_meta(meta: List[dict], get: Getter) -> Tuple[SourceMap, int]:
    """Lädt alle Meta-Quellen -> (gefundene Quellen, Anzahl erfolgreich geladener Meta-Quellen)."""

    async def one(entry: dict) -> Optional[SourceMap]:
        parser = META_PARSERS.get(entry.get("format", "url-list"))
        if not parser:
            return None
        try:
            return parser(await get(entry["url"], timeout=20), entry)
        except Exception:  # Meta-Quelle nicht erreichbar -> nur weniger Quellen, kein Abbruch
            return None

    found: SourceMap = {}
    ok = 0
    for res in await asyncio.gather(*(one(m) for m in meta)):
        if res is not None:
            ok += 1
            for url, ptype in res.items():
                found.setdefault(url, ptype)
    return found, ok


# --------------------------------------------------------------------------- #
# GitHub-Discovery
# --------------------------------------------------------------------------- #

DISCOVERY_QUERIES = (
    "topic:proxy-list",
    "topic:free-proxy-list",
    "topic:proxy-lists",
    "topic:free-proxy",
    "topic:socks5-proxy",
    "topic:http-proxy-list",
    "proxy list in:name",
    "free proxy in:name,description",
    "proxies in:name",
)
# Pfade, die zwar auf .txt enden, aber keine (vollständigen) Proxy-Listen sind:
# VPN-Konfigs, Länder-/ASN-Aufteilungen (nur Teilmengen), Archive, Blocklisten …
_PATH_REJECT_RE = re.compile(
    r"(v2ray|vmess|vless|trojan|shadowsocks|(^|[/_\-])ssr?([/_\-.]|$)|clash|mtproto|wireguard|hysteria|tuic"
    r"|readme|license|requirements|block|countr|geo|/asn/|archive|history|backup|old/|test"
    r"|(^|/)[a-z]{2}\.txt$)"
)
_PATH_TYPE_RE = re.compile(r"(socks5|socks4|https?)")
_FILE_GENERIC_RE = re.compile(r"(^|[/_\-.])(proxy|proxies|all)[^/]*\.txt$")
MAX_FILES_PER_REPO = 12
MAX_REPOS_PER_OWNER = 3  # gegen Spam-Konten mit Dutzenden identischer Klon-Repos


def classify_path(path: str) -> Optional[str]:
    """Proxy-Typ einer Datei anhand ihres Pfads, oder None, wenn sie nicht nach Proxy-Liste aussieht."""
    p = path.lower()
    if not p.endswith(".txt") or p.count("/") > 3 or _PATH_REJECT_RE.search(p):
        return None
    m = _PATH_TYPE_RE.search(p)
    if m:
        return TYPE_ALIASES[m[1]]
    return "auto" if _FILE_GENERIC_RE.search(p) else None


def github_token() -> Optional[str]:
    """Token aus GITHUB_TOKEN/GH_TOKEN oder der gh-CLI – hebt das API-Limit von 60 auf 5000 Anfragen/h."""
    for key in ("GITHUB_TOKEN", "GH_TOKEN"):
        if os.environ.get(key):
            return os.environ[key].strip()
    try:
        res = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    if res.returncode != 0:
        return None
    return res.stdout.strip() or None


async def discover_github(
    get: Getter,
    token: Optional[str],
    max_repos: int,
    days: int = 3,
    on_progress: Optional[Callable[[str], None]] = None,
) -> SourceMap:
    """Sucht aktiv gepflegte Proxy-Listen-Repos und deren Listendateien."""
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")

    repos: Dict[str, Tuple[str, int]] = {}
    for q in DISCOVERY_QUERIES:
        for page in (1, 2):
            query = urlencode({"q": f"{q} pushed:>{since}", "sort": "stars", "per_page": 100, "page": page})
            try:
                data = json.loads(await get(f"https://api.github.com/search/repositories?{query}", headers=headers))
            except Exception:  # Rate-Limit o. ä. – mit dem weitermachen, was schon da ist
                break
            items = data.get("items", [])
            for it in items:
                repos.setdefault(it["full_name"], (it["default_branch"], it["stargazers_count"]))
            if on_progress:
                on_progress(f"{len(repos)} Repos gefunden")
            if len(items) < 100:
                break

    per_owner: Counter = Counter()
    chosen: List[Tuple[str, str]] = []
    for name, (branch, _stars) in sorted(repos.items(), key=lambda kv: -kv[1][1]):
        owner = name.split("/", 1)[0].lower()
        if per_owner[owner] < MAX_REPOS_PER_OWNER:
            per_owner[owner] += 1
            chosen.append((name, branch))
    chosen = chosen[:max_repos]

    sem = asyncio.Semaphore(8)
    done = 0

    async def scan(name: str, branch: str) -> SourceMap:
        nonlocal done
        url = f"https://api.github.com/repos/{name}/git/trees/{quote(branch, safe='')}?recursive=1"
        async with sem:
            try:
                tree = json.loads(await get(url, headers=headers, timeout=30)).get("tree", [])
            except Exception:
                tree = []
        done += 1
        if on_progress:
            on_progress(f"{done}/{len(chosen)} Repos durchsucht")
        files = []
        for entry in tree:
            if entry.get("type") == "blob" and entry.get("size", 0) >= 200:
                ptype = classify_path(entry["path"])
                if ptype:
                    files.append((entry["path"].count("/"), entry["path"], ptype))
        files.sort()  # flache Pfade zuerst – die sind meist die Gesamtlisten
        return {
            f"{GH_RAW}/{name}/{branch}/{quote(path)}": ptype
            for _depth, path, ptype in files[:MAX_FILES_PER_REPO]
        }

    found: SourceMap = {}
    for res in await asyncio.gather(*(scan(n, b) for n, b in chosen)):
        found.update(res)
    return found


# --------------------------------------------------------------------------- #
# Qualität pro Quelle lernen
# --------------------------------------------------------------------------- #

DAY = 86400.0
DECAY = 0.5                 # ältere Läufe zählen je Lauf nur noch halb
PRIOR_HITS, PRIOR_MISSES = 1.0, 30.0   # neue Quellen starten bei ~3 % Trefferquote
STALE_AFTER = 7 * DAY       # Inhalt seit einer Woche unverändert -> Liste wird nicht mehr gepflegt
DEAD_MIN_CHECKED = 300      # so viele Prüfungen ohne Treffer -> Quelle gilt als tot
UNREACHABLE_STREAK = 3      # so oft hintereinander nicht ladbar -> Pause
UNREACHABLE_PAUSE = 2 * DAY


@dataclass
class SourceRecord:
    first_seen: float = 0.0
    last_fetch: float = 0.0
    fail_streak: int = 0
    count: int = 0
    content_hash: str = ""
    last_change: float = 0.0
    checked: float = 0.0  # abklingende Summen über die Läufe
    working: float = 0.0
    runs: int = 0

    @property
    def score(self) -> float:
        """Geschätzte Trefferquote (Bayes-geglättet, damit 1 von 1 nicht 100 % bedeutet)."""
        return (self.working + PRIOR_HITS) / (self.checked + PRIOR_HITS + PRIOR_MISSES)


class SourceStats:
    def __init__(self, path: Path = STATS_FILE):
        self.path = path
        self.records: Dict[str, SourceRecord] = {}
        if path.exists():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                self.records = {url: SourceRecord(**rec) for url, rec in raw.items()}
            except (OSError, ValueError, TypeError) as e:
                # Kaputte Statistik ist kein Grund abzubrechen – dann wird eben neu gelernt
                warnings.warn(f"{path.name} unlesbar ({e}), starte ohne Quellen-Statistik")

    def get(self, url: str) -> SourceRecord:
        return self.records.get(url) or SourceRecord()

    def score(self, url: str) -> float:
        return self.get(url).score

    def skip_reason(self, url: str, now: Optional[float] = None) -> Optional[str]:
        rec = self.records.get(url)
        if rec is None:
            return None
        now = time.time() if now is None else now
        if rec.fail_streak >= UNREACHABLE_STREAK and now - rec.last_fetch < UNREACHABLE_PAUSE:
            return "unerreichbar"
        if rec.last_change and now - rec.last_change > STALE_AFTER and now - rec.first_seen > STALE_AFTER:
            return "veraltet"
        if rec.runs >= 2 and rec.checked >= DEAD_MIN_CHECKED and rec.working < 0.5:
            return "tot"
        return None

    def record_fetch(self, url: str, data: Optional[bytes], count: int, now: Optional[float] = None) -> None:
        now = time.time() if now is None else now
        rec = self.records.setdefault(url, SourceRecord(first_seen=now))
        rec.last_fetch = now
        if data is None or count == 0:
            rec.fail_streak += 1
            return
        rec.fail_streak = 0
        rec.count = count
        digest = hashlib.sha1(data).hexdigest()
        if digest != rec.content_hash:
            rec.content_hash = digest
            rec.last_change = now

    def record_checks(self, results: Dict[str, Tuple[int, int]]) -> None:
        """results: url -> (geprüft, funktionierend) in diesem Lauf."""
        for url, (checked, working) in results.items():
            if not checked:
                continue
            rec = self.records.setdefault(url, SourceRecord(first_seen=time.time()))
            rec.checked = rec.checked * DECAY + checked
            rec.working = rec.working * DECAY + working
            rec.runs += 1

    def ranking(self, urls: Iterable[str]) -> List[Tuple[str, SourceRecord]]:
        return sorted(((u, self.get(u)) for u in urls), key=lambda x: -x[1].score)

    def save(self) -> None:
        payload = {url: asdict(rec) for url, rec in sorted(self.records.items())}
        atomic_write(self.path, json.dumps(payload, indent=1))
