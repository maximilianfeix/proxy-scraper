"""Alle Einstellungen eines Laufs an einer Stelle – egal ob sie von der Kommandozeile oder
aus dem Einrichtungsassistenten kommen."""

from __future__ import annotations

import shlex
from dataclasses import dataclass, field
from typing import List, Optional, Set

from .checker import ANONYMITY_RANK, CheckResult
from .parsing import PROXY_TYPES

DEFAULT_CONCURRENCY = 2000
DEFAULT_TIMEOUT = 8.0
DEFAULT_CONNECT_TIMEOUT = 4.0
DEFAULT_DISCOVER_REPOS = 400


def parse_countries(value: Optional[str]) -> Set[str]:
    """'de, at,CH' -> {'DE', 'AT', 'CH'}"""
    return {c.strip().upper() for c in (value or "").split(",") if c.strip()}


@dataclass
class Filters:
    countries: Set[str] = field(default_factory=set)
    https_only: bool = False
    min_anonymity: str = ""
    max_latency: int = 0

    @property
    def needs_details(self) -> bool:
        return self.https_only or bool(self.min_anonymity)

    @property
    def active(self) -> bool:
        return bool(self.countries or self.https_only or self.min_anonymity or self.max_latency)

    def accepts(self, r: CheckResult) -> bool:
        if self.max_latency and r.latency > self.max_latency:
            return False
        if self.https_only and r.https is not True:
            return False
        if self.min_anonymity and ANONYMITY_RANK.get(r.anonymity, -1) < ANONYMITY_RANK[self.min_anonymity]:
            return False
        if self.countries and r.country not in self.countries:
            return False
        return True

    def describe(self) -> str:
        parts = []
        if self.countries:
            parts.append("Land " + ",".join(sorted(self.countries)))
        if self.https_only:
            parts.append("nur HTTPS")
        if self.min_anonymity:
            parts.append(f"mind. {self.min_anonymity}")
        if self.max_latency:
            parts.append(f"≤ {self.max_latency} ms")
        return " · ".join(parts)


@dataclass
class RunOptions:
    types: List[str] = field(default_factory=lambda: list(PROXY_TYPES))
    filters: Filters = field(default_factory=Filters)
    want: int = 0
    limit: int = 0
    fast: bool = False
    no_geo: bool = False
    recheck: Optional[str] = None
    output: Optional[str] = None
    concurrency: int = DEFAULT_CONCURRENCY
    timeout: float = DEFAULT_TIMEOUT
    connect_timeout: float = DEFAULT_CONNECT_TIMEOUT
    discover: bool = False
    no_discover: bool = False
    discover_repos: int = DEFAULT_DISCOVER_REPOS
    all_sources: bool = False

    def __post_init__(self) -> None:
        unknown = set(self.types) - set(PROXY_TYPES)
        if unknown:
            raise ValueError(f"unbekannte Proxy-Typen: {', '.join(sorted(unknown))}")
        # Die Typen sind fachlich eine Menge: feste Reihenfolge, keine Duplikate.
        # Sonst ergäben "--types socks5 http" und "--types http socks5" verschiedene Einstellungen.
        self.types = [t for t in PROXY_TYPES if t in self.types]
        if not self.types:
            raise ValueError("mindestens ein Proxy-Typ nötig")  # sonst wäre to_argv() "--types" ohne Wert
        if self.concurrency < 1:
            raise ValueError("concurrency muss mindestens 1 sein")
        if self.timeout <= 0 or self.connect_timeout <= 0:
            raise ValueError("Timeouts müssen größer als 0 sein")
        if min(self.want, self.limit, self.discover_repos, self.filters.max_latency) < 0:
            raise ValueError("Mengen und Latenz dürfen nicht negativ sein")

    @property
    def details(self) -> bool:
        """HTTPS- und Anonymitätstest – abschaltbar, außer ein Filter braucht sie."""
        return not self.fast or self.filters.needs_details

    @property
    def geo(self) -> bool:
        return not self.no_geo or bool(self.filters.countries)

    @classmethod
    def from_args(cls, args) -> "RunOptions":
        return cls(
            types=list(args.types),
            filters=Filters(
                countries=parse_countries(args.country),
                https_only=args.https_only,
                min_anonymity=args.anonymity or "",
                max_latency=args.max_latency,
            ),
            want=args.want,
            limit=args.limit,
            fast=args.fast,
            no_geo=args.no_geo,
            recheck=args.recheck,
            output=args.output,
            concurrency=args.concurrency,
            timeout=args.timeout,
            connect_timeout=args.connect_timeout,
            discover=args.discover,
            no_discover=args.no_discover,
            discover_repos=args.discover_repos,
            all_sources=args.all_sources,
        )

    def to_argv(self) -> List[str]:
        """Kommandozeilen-Argumente, die genau diese Einstellungen ergeben (nur Abweichungen vom Standard)."""
        argv: List[str] = []
        if self.types != list(PROXY_TYPES):
            argv += ["--types", *self.types]
        f = self.filters
        if f.countries:
            argv += ["--country", ",".join(sorted(f.countries))]
        if f.https_only:
            argv.append("--https-only")
        if f.min_anonymity:
            argv += ["--anonymity", f.min_anonymity]
        if f.max_latency:
            argv += ["--max-latency", str(f.max_latency)]
        _opt(argv, "--want", self.want, 0)
        _opt(argv, "--limit", self.limit, 0)
        _flag(argv, "--fast", self.fast)
        _flag(argv, "--no-geo", self.no_geo)
        if self.recheck is not None:
            argv += ["--recheck", self.recheck] if self.recheck else ["--recheck"]
        if self.output:
            argv += ["--output", self.output]
        _opt(argv, "--concurrency", self.concurrency, DEFAULT_CONCURRENCY)
        _opt(argv, "--timeout", self.timeout, DEFAULT_TIMEOUT)
        _opt(argv, "--connect-timeout", self.connect_timeout, DEFAULT_CONNECT_TIMEOUT)
        _flag(argv, "--discover", self.discover)
        _flag(argv, "--no-discover", self.no_discover)
        _opt(argv, "--discover-repos", self.discover_repos, DEFAULT_DISCOVER_REPOS)
        _flag(argv, "--all-sources", self.all_sources)
        return argv

    def to_command(self, program: str = "python3 proxy_scraper.py") -> str:
        return " ".join([program, *map(shlex.quote, self.to_argv())])


def _opt(argv: List[str], name: str, value, default) -> None:
    if value != default:
        argv += [name, f"{value:g}" if isinstance(value, float) else str(value)]


def _flag(argv: List[str], name: str, value: bool) -> None:
    if value:
        argv.append(name)

