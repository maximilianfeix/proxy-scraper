"""
Source management for the proxy scraper:

- loads the curated source list (sources.json) and sources found with --discover,
- resolves meta sources (lists of source URLs maintained by others),
- finds new proxy lists on GitHub,
- remembers per source how many of its proxies really work, and
  skips dead, outdated or unreachable sources.
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
from .paths import DATA_DIR, PACKAGE_DIR, atomic_write

SOURCES_FILE = PACKAGE_DIR / "sources.json"
DISCOVERED_FILE = DATA_DIR / "sources_discovered.json"
STATS_FILE = DATA_DIR / "source_stats.json"

GH_RAW = "https://raw.githubusercontent.com"
# "auto" = the list contains type://ip:port lines, the type is given per line
SOURCE_TYPES = (*PROXY_TYPES, "auto")

# url -> Typ
SourceMap = Dict[str, str]
Getter = Callable[..., Awaitable[bytes]]


# --------------------------------------------------------------------------- #
# URLs & source lists
# --------------------------------------------------------------------------- #

_GH_BLOB_RE = re.compile(r"^https://github\.com/([^/]+)/([^/]+)/(?:raw|blob)/(?:refs/heads/)?(.+)$")


def normalize_url(url: str) -> Optional[str]:
    """Normalizes source URLs so the same file isn't loaded several times.

    github.com/…/raw/… -> raw.githubusercontent.com/…, '/refs/heads/' is dropped,
    format suffixes like ',,ColonURL' are cut off. Templates with {…} -> None.
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
    """Reads sources.json -> (sources, meta sources)."""
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
    """Age of the last discovery in days, None if there hasn't been one yet."""
    try:
        generated = json.loads(path.read_text(encoding="utf-8"))["generated"]
        return (datetime.now(timezone.utc) - datetime.fromisoformat(generated)).total_seconds() / DAY
    except (OSError, ValueError, KeyError, TypeError):
        return None


def save_discovered(sources: SourceMap, path: Path = DISCOVERED_FILE) -> None:
    payload = {"generated": datetime.now(timezone.utc).isoformat(timespec="seconds"), "sources": sources}
    atomic_write(path, json.dumps(payload, indent=1, sort_keys=True))


# --------------------------------------------------------------------------- #
# meta sources: lists of source URLs maintained by others
# --------------------------------------------------------------------------- #

def parse_url_list(data: bytes, ptype: str) -> SourceMap:
    """One source URL per line (e.g. gfpcom/free-proxy-list/sources/http.txt)."""
    out: SourceMap = {}
    for line in data.decode("utf-8", "ignore").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            _add(out, line, ptype)
    return out


_TOML_SECTION_RE = re.compile(r"^\s*\[scraping\.(\w+)\]")
_TOML_URL_RE = re.compile(r'"(https?://[^"]+)"')


def parse_monosans_toml(data: bytes) -> SourceMap:
    """URLs from the [scraping.<type>] sections of monosans/proxy-scraper-checker's config.toml.

    Python 3.9 has no tomllib – a line parser is enough for this flat structure.
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
    """Loads every meta source -> (sources found, number of meta sources loaded successfully)."""

    async def one(entry: dict) -> Optional[SourceMap]:
        parser = META_PARSERS.get(entry.get("format", "url-list"))
        if not parser:
            return None
        try:
            return parser(await get(entry["url"], timeout=20), entry)
        except Exception:  # meta source unreachable -> just fewer sources, no abort
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
# paths that end in .txt but aren't (complete) proxy lists:
# VPN configs, splits by country/ASN (subsets only), archives, blocklists …
_PATH_REJECT_RE = re.compile(
    r"(v2ray|vmess|vless|trojan|shadowsocks|(^|[/_\-])ssr?([/_\-.]|$)|clash|mtproto|wireguard|hysteria|tuic"
    r"|readme|license|requirements|block|countr|geo|/asn/|archive|history|backup|old/|test"
    r"|(^|/)[a-z]{2}\.txt$)"
)
_PATH_TYPE_RE = re.compile(r"(socks5|socks4|https?)")
_FILE_GENERIC_RE = re.compile(r"(^|[/_\-.])(proxy|proxies|all)[^/]*\.txt$")
MAX_FILES_PER_REPO = 12
MAX_REPOS_PER_OWNER = 3  # against spam accounts with dozens of identical clone repos


def classify_path(path: str) -> Optional[str]:
    """Proxy type of a file from its path, or None if it doesn't look like a proxy list."""
    p = path.lower()
    if not p.endswith(".txt") or p.count("/") > 3 or _PATH_REJECT_RE.search(p):
        return None
    m = _PATH_TYPE_RE.search(p)
    if m:
        return TYPE_ALIASES[m[1]]
    return "auto" if _FILE_GENERIC_RE.search(p) else None


def github_token() -> Optional[str]:
    """Token from GITHUB_TOKEN/GH_TOKEN or the gh CLI – raises the API limit from 60 to 5000 requests/h."""
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
    """Looks for actively maintained proxy list repos and their list files."""
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
            except Exception:  # rate limit or similar – carry on with what we already have
                break
            items = data.get("items", [])
            for it in items:
                repos.setdefault(it["full_name"], (it["default_branch"], it["stargazers_count"]))
            if on_progress:
                on_progress(f"{len(repos)} repos found")
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
        files.sort()  # shallow paths first – those are usually the complete lists
        return {
            f"{GH_RAW}/{name}/{branch}/{quote(path)}": ptype
            for _depth, path, ptype in files[:MAX_FILES_PER_REPO]
        }

    found: SourceMap = {}
    for res in await asyncio.gather(*(scan(n, b) for n, b in chosen)):
        found.update(res)
    return found


# --------------------------------------------------------------------------- #
# learning the quality of each source
# --------------------------------------------------------------------------- #

DAY = 86400.0
DECAY = 0.5                 # older runs count half as much with every run
PRIOR_HITS, PRIOR_MISSES = 1.0, 30.0   # new sources start at a ~3 % hit rate
STALE_AFTER = 7 * DAY       # content unchanged for a week -> the list is no longer maintained
DEAD_MIN_CHECKED = 300      # this many checks without a hit -> the source counts as dead
UNREACHABLE_STREAK = 3      # failed to load this many times in a row -> pause
UNREACHABLE_PAUSE = 2 * DAY


@dataclass
class SourceRecord:
    first_seen: float = 0.0
    last_fetch: float = 0.0
    fail_streak: int = 0
    count: int = 0
    content_hash: str = ""
    last_change: float = 0.0
    checked: float = 0.0  # decaying sums over the runs
    working: float = 0.0
    runs: int = 0

    @property
    def score(self) -> float:
        """Estimated hit rate (Bayesian smoothing, so 1 out of 1 doesn't mean 100 %)."""
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
                # broken statistics are no reason to abort – we just learn again
                warnings.warn(f"{path.name} unreadable ({e}), starting without source statistics", stacklevel=2)

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
            return "unreachable"
        if rec.last_change and now - rec.last_change > STALE_AFTER and now - rec.first_seen > STALE_AFTER:
            return "outdated"
        if rec.runs >= 2 and rec.checked >= DEAD_MIN_CHECKED and rec.working < 0.5:
            return "dead"
        return None

    def record_fetch(self, url: str, data: Optional[bytes], count: int, now: Optional[float] = None,
                     unchanged: bool = False) -> None:
        """unchanged=True: the server answered 304 – reachable, same content as last time.
        Hash and last_change stay as they are, so the outdated detection keeps working normally."""
        now = time.time() if now is None else now
        rec = self.records.setdefault(url, SourceRecord(first_seen=now))
        rec.last_fetch = now
        if unchanged:  # also with 0 matching proxies (e.g. other --types): the source did answer
            rec.fail_streak = 0
            rec.count = count
            return
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
        """results: url -> (checked, working) in this run."""
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
