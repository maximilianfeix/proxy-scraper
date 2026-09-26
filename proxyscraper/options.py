"""All settings of a run in one place – whether they come from the command line or
from the setup wizard."""

from __future__ import annotations

import shlex
from dataclasses import dataclass, field
from typing import List, Optional, Set

from .checker import ANONYMITY_RANK, CheckResult
from .exporters import EXPORTERS
from .parsing import PROXY_TYPES
from .paths import is_checkout
from .server.pool import STRATEGIES
from .targets import target_label

DEFAULT_CONCURRENCY = 2000
DEFAULT_TIMEOUT = 8.0
DEFAULT_CONNECT_TIMEOUT = 4.0
DEFAULT_DISCOVER_REPOS = 400
DEFAULT_SERVE_PORT = 8899
STDOUT = "-"  # -o -: hits to stdout


def parse_countries(value: Optional[str]) -> Set[str]:
    """'de, at,CH' -> {'DE', 'AT', 'CH'}"""
    return {c.strip().upper() for c in (value or "").split(",") if c.strip()}


@dataclass
class Filters:
    countries: Set[str] = field(default_factory=set)
    https_only: bool = False
    min_anonymity: str = ""
    max_latency: int = 0
    targets: List[str] = field(default_factory=list)  # target sites every proxy has to reach
    no_datacenter: bool = False  # only exits that are not (recognizably) in a datacenter
    no_blocklisted: bool = False  # only exits that are not on the SpamCop blocklist

    @property
    def needs_details(self) -> bool:
        # anonymity comes from the confirmation (always runs) – HTTPS and target sites need the detail test
        return self.https_only or bool(self.targets)

    @property
    def active(self) -> bool:
        return bool(self.countries or self.https_only or self.min_anonymity or self.max_latency or self.targets
                    or self.no_datacenter or self.no_blocklisted)

    def accepts(self, r: CheckResult) -> bool:
        if self.max_latency and r.latency > self.max_latency:
            return False
        if self.https_only and r.https is not True:
            return False
        if self.min_anonymity and ANONYMITY_RANK.get(r.anonymity, -1) < ANONYMITY_RANK[self.min_anonymity]:
            return False
        if self.countries and r.country not in self.countries:
            return False
        if self.no_datacenter and r.hosting:
            return False
        if self.no_blocklisted and r.blocklisted:
            return False
        return all(r.targets.get(url) for url in self.targets)  # reached every requested target site

    def may_pass(self, r: CheckResult) -> bool:
        """Can `r` still pass the filters? HTTPS is still unknown at this point, possibly the country too.

        Whatever is sure to fail already doesn't need an expensive HTTPS test any more.
        """
        if self.max_latency and r.latency > self.max_latency:
            return False
        if self.min_anonymity and ANONYMITY_RANK.get(r.anonymity, -1) < ANONYMITY_RANK[self.min_anonymity]:
            return False
        if self.no_datacenter and r.hosting:
            return False
        if self.no_blocklisted and r.blocklisted:
            return False
        # country still unknown -> may still match
        return not self.countries or not r.country or r.country in self.countries

    def describe(self) -> str:
        parts = []
        if self.countries:
            parts.append("country " + ",".join(sorted(self.countries)))
        if self.https_only:
            parts.append("HTTPS only")
        if self.min_anonymity:
            parts.append(f"min. {self.min_anonymity}")
        if self.max_latency:
            parts.append(f"≤ {self.max_latency} ms")
        if self.targets:
            parts.append("target " + ", ".join(target_label(u, self.targets) for u in self.targets))
        if self.no_datacenter:
            parts.append("no datacenters")
        if self.no_blocklisted:
            parts.append("not blocklisted")
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
    exports: List[str] = field(default_factory=list)  # extra formats, see exporters.py
    concurrency: int = DEFAULT_CONCURRENCY
    timeout: float = DEFAULT_TIMEOUT
    connect_timeout: float = DEFAULT_CONNECT_TIMEOUT
    discover: bool = False
    no_discover: bool = False
    discover_repos: int = DEFAULT_DISCOVER_REPOS
    all_sources: bool = False
    no_cache: bool = False  # reload every list instead of taking unchanged ones from the cache
    no_dnsbl: bool = False  # skip the blocklist lookup of the exit IPs
    serve: int = 0  # port of the rotating proxy server after the run, 0 = off
    rotate: str = "weighted"  # strategy of the proxy server, see server/pool.py
    sticky: int = 0  # seconds a target site keeps the same proxy (0 = new one for every connection)
    serve_host: str = "127.0.0.1"  # address of the proxy server; anything else is reachable from outside
    serve_password: str = field(default="", repr=False)  # required from clients if set; never written to argv
    serve_refill: float = 0  # hours between background refills of the proxy server's pool, 0 = off

    def __post_init__(self) -> None:
        unknown = set(self.types) - set(PROXY_TYPES)
        if unknown:
            raise ValueError(f"unknown proxy types: {', '.join(sorted(unknown))}")
        # the types are really a set: fixed order, no duplicates.
        # Otherwise "--types socks5 http" and "--types http socks5" would give different settings.
        self.types = [t for t in PROXY_TYPES if t in self.types]
        if not self.types:
            raise ValueError("at least one proxy type needed")  # else to_argv() gives "--types" without a value
        if self.concurrency < 1:
            raise ValueError("concurrency must be at least 1")
        if self.timeout <= 0 or self.connect_timeout <= 0:
            raise ValueError("timeouts must be greater than 0")
        if min(self.want, self.limit, self.discover_repos, self.filters.max_latency) < 0:
            raise ValueError("amounts and latency must not be negative")
        unknown_exports = set(self.exports) - set(EXPORTERS)
        if unknown_exports:
            raise ValueError(f"unknown export formats: {', '.join(sorted(unknown_exports))}")
        self.exports = [e for e in EXPORTERS if e in self.exports]
        if self.rotate not in STRATEGIES:
            raise ValueError(f"unknown strategy: {self.rotate}")
        if self.sticky < 0:
            raise ValueError("--sticky must not be negative")
        if self.serve_refill < 0:
            raise ValueError("--serve-refill must not be negative")
        if not 0 <= self.serve <= 65535:
            raise ValueError("port must be between 1 and 65535")

    @property
    def details(self) -> bool:
        """HTTPS test – can be switched off (--fast), unless the HTTPS filter needs it."""
        return not self.fast or self.filters.needs_details

    @property
    def check_timeout(self) -> float:
        """Timeout of the basic check: whatever exceeds the latency limit drops out anyway –
        nobody needs to wait that long. With 2000 parallel slots that's a lot more throughput."""
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
                no_datacenter=args.no_datacenter,
                no_blocklisted=args.no_blocklisted,
            ),
            want=args.want,
            limit=args.limit,
            fast=args.fast,
            no_geo=args.no_geo,
            recheck=args.recheck,
            output=args.output,
            exports=list(args.export or []),
            concurrency=args.concurrency,
            timeout=args.timeout,
            connect_timeout=args.connect_timeout,
            discover=args.discover,
            no_discover=args.no_discover,
            discover_repos=args.discover_repos,
            all_sources=args.all_sources,
            no_cache=args.no_cache,
            no_dnsbl=args.no_dnsbl,
            serve=args.serve,
            rotate=args.rotate,
            sticky=args.sticky,
            serve_host=args.serve_host,
            serve_password=args.serve_password,
            serve_refill=args.serve_refill,
        )

    def to_argv(self) -> List[str]:
        """Command line arguments that produce exactly these settings (only deviations from the defaults)."""
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
        _flag(argv, "--no-datacenter", f.no_datacenter)
        _flag(argv, "--no-blocklisted", f.no_blocklisted)
        _opt(argv, "--want", self.want, 0)
        _opt(argv, "--limit", self.limit, 0)
        _flag(argv, "--fast", self.fast)
        _flag(argv, "--no-geo", self.no_geo)
        if self.recheck is not None:
            argv += ["--recheck", self.recheck] if self.recheck else ["--recheck"]
        if self.output:
            argv += ["--output", self.output]
        if self.exports:
            argv += ["--export", ",".join(self.exports)]
        _opt(argv, "--concurrency", self.concurrency, DEFAULT_CONCURRENCY)
        _opt(argv, "--timeout", self.timeout, DEFAULT_TIMEOUT)
        _opt(argv, "--connect-timeout", self.connect_timeout, DEFAULT_CONNECT_TIMEOUT)
        _flag(argv, "--discover", self.discover)
        _flag(argv, "--no-discover", self.no_discover)
        _opt(argv, "--discover-repos", self.discover_repos, DEFAULT_DISCOVER_REPOS)
        _flag(argv, "--all-sources", self.all_sources)
        _flag(argv, "--no-cache", self.no_cache)
        _flag(argv, "--no-dnsbl", self.no_dnsbl)
        if self.serve:
            argv += ["--serve"] if self.serve == DEFAULT_SERVE_PORT else ["--serve", str(self.serve)]
        if self.rotate != "weighted":
            argv += ["--rotate", self.rotate]
        if self.serve_host != "127.0.0.1":
            argv += ["--serve-host", self.serve_host]
        _opt(argv, "--sticky", self.sticky, 0)
        _opt(argv, "--serve-refill", float(self.serve_refill), 0.0)
        return argv

    def to_command(self, program: Optional[str] = None) -> str:
        if program is None:  # started from the repo or installed?
            program = "python3 proxy_scraper.py" if is_checkout() else "proxy-scraper"
        return " ".join([program, *map(shlex.quote, self.to_argv())])


def _opt(argv: List[str], name: str, value, default) -> None:
    if value != default:
        argv += [name, f"{value:g}" if isinstance(value, float) else str(value)]


def _flag(argv: List[str], name: str, value: bool) -> None:
    if value:
        argv.append(name)

