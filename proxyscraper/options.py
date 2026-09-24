"""Alle Einstellungen eines Laufs an einer Stelle – egal ob sie von der Kommandozeile oder
aus dem Einrichtungsassistenten kommen."""

from __future__ import annotations

import shlex
from dataclasses import dataclass, field
from typing import List, Optional, Set

from .checker import ANONYMITY_RANK, CheckResult
from .parsing import PROXY_TYPES
from .paths import is_checkout
from .targets import target_label

DEFAULT_CONCURRENCY = 2000
DEFAULT_TIMEOUT = 8.0
DEFAULT_CONNECT_TIMEOUT = 4.0
DEFAULT_DISCOVER_REPOS = 400
DEFAULT_SERVE_PORT = 8899


def parse_countries(value: Optional[str]) -> Set[str]:
    """'de, at,CH' -> {'DE', 'AT', 'CH'}"""
    return {c.strip().upper() for c in (value or "").split(",") if c.strip()}


@dataclass
class Filters:
    countries: Set[str] = field(default_factory=set)
    https_only: bool = False
    min_anonymity: str = ""
    max_latency: int = 0
    targets: List[str] = field(default_factory=list)  # Zielseiten, die jeder Proxy erreichen muss

    @property
    def needs_details(self) -> bool:
        # Die Anonymität kommt aus der Bestätigung (läuft immer) – HTTPS und Zielseiten brauchen den Detailtest
        return self.https_only or bool(self.targets)

    @property
    def active(self) -> bool:
        return bool(self.countries or self.https_only or self.min_anonymity or self.max_latency or self.targets)

    def accepts(self, r: CheckResult) -> bool:
        if self.max_latency and r.latency > self.max_latency:
            return False
        if self.https_only and r.https is not True:
            return False
        if self.min_anonymity and ANONYMITY_RANK.get(r.anonymity, -1) < ANONYMITY_RANK[self.min_anonymity]:
            return False
        if self.countries and r.country not in self.countries:
            return False
        if any(not r.targets.get(url) for url in self.targets):
            return False
        return True

    def may_pass(self, r: CheckResult) -> bool:
        """Kann `r` die Filter noch erfüllen? HTTPS ist an dieser Stelle noch unbekannt, das Land evtl. auch.

        Wer schon jetzt sicher durchfällt, braucht keinen teuren HTTPS-Test mehr.
        """
        if self.max_latency and r.latency > self.max_latency:
            return False
        if self.min_anonymity and ANONYMITY_RANK.get(r.anonymity, -1) < ANONYMITY_RANK[self.min_anonymity]:
            return False
        if self.countries and r.country and r.country not in self.countries:
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
        if self.targets:
            parts.append("Ziel " + ", ".join(target_label(u, self.targets) for u in self.targets))
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
    serve: int = 0  # Port des rotierenden Proxy-Servers nach dem Lauf, 0 = aus

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
        if not 0 <= self.serve <= 65535:
            raise ValueError("Port muss zwischen 1 und 65535 liegen")

    @property
    def details(self) -> bool:
        """HTTPS-Test – abschaltbar (--fast), außer der HTTPS-Filter braucht ihn."""
        return not self.fast or self.filters.needs_details

    @property
    def check_timeout(self) -> float:
        """Timeout der Basisprüfung: Wer das Latenzlimit überschreitet, fliegt ohnehin raus –
        so lange muss niemand warten. Bei 2000 parallelen Slots ist das deutlich mehr Durchsatz."""
        if self.filters.max_latency:
            return min(self.timeout, self.filters.max_latency / 1000)
        return self.timeout

    @property
    def check_connect_timeout(self) -> float:
        return min(self.connect_timeout, self.check_timeout)

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
                targets=list(dict.fromkeys(args.target or [])),
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
            serve=args.serve,
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
        for url in f.targets:
            argv += ["--target", url]
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
        if self.serve:
            argv += ["--serve"] if self.serve == DEFAULT_SERVE_PORT else ["--serve", str(self.serve)]
        return argv

    def to_command(self, program: Optional[str] = None) -> str:
        if program is None:  # aus dem Repo gestartet oder installiert?
            program = "python3 proxy_scraper.py" if is_checkout() else "proxy-scraper"
        return " ".join([program, *map(shlex.quote, self.to_argv())])


def _opt(argv: List[str], name: str, value, default) -> None:
    if value != default:
        argv += [name, f"{value:g}" if isinstance(value, float) else str(value)]


def _flag(argv: List[str], name: str, value: bool) -> None:
    if value:
        argv.append(name)

