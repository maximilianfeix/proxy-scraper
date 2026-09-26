"""SVG charts of the live list for the README: the working proxies over the last week, stacked by protocol,
and where they are. Written with every run next to the list, so the README shows today's numbers.

Plain SVG without scripts or web fonts – GitHub shows README images through a proxy that allows neither.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Sequence, Tuple
from xml.sax.saxutils import escape

from .pages import COUNTRIES
from .parsing import PROXY_TYPES

THEMES = {
    "dark": {"bg": "#121113", "panel": "#1A191C", "line": "#2B292F", "text": "#EDEBE6", "muted": "#9A97A0",
             "http": "#8DB8FF", "socks4": "#C7A6FF", "socks5": "#D4F77A"},
    "light": {"bg": "#FFFFFF", "panel": "#F6F6F3", "line": "#DAD9D4", "text": "#121113", "muted": "#5F5C66",
              "http": "#1F5FD1", "socks4": "#7442D6", "socks5": "#3F5A00"},
}
FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif"
WIDTH, HEIGHT = 880, 300
DAYS = 7


def _when(run: dict) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(run["updated"])
    except (KeyError, TypeError, ValueError):
        return None


def recent_runs(runs: Sequence[dict], now: datetime, days: int = DAYS) -> List[Tuple[datetime, dict]]:
    """The runs of the last `days`, oldest first. Runs less than 20 minutes apart (a manual run right after the
    hourly one) count once, the later one wins – otherwise the chart gets spikes that mean nothing."""
    since = now - timedelta(days=days)
    timed = sorted(((t, r) for r in runs if (t := _when(r)) and t > since and isinstance(r.get("by_type"), dict)),
                   key=lambda x: x[0])
    kept: List[Tuple[datetime, dict]] = []
    for t, r in timed:
        if kept and t - kept[-1][0] < timedelta(minutes=20):
            kept[-1] = (t, r)
        else:
            kept.append((t, r))
    return kept


def _num(n: int) -> str:
    return f"{n:,}"


def trend_svg(runs: Sequence[dict], now: datetime, theme: str = "dark") -> str:
    """Working proxies per run over the last week, stacked by protocol, with today's total as the headline."""
    c = THEMES[theme]
    points = recent_runs(runs, now)
    left, right, top, bottom = 250, WIDTH - 24, 36, HEIGHT - 44
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" '
             f'viewBox="0 0 {WIDTH} {HEIGHT}" '
             f'font-family="{FONT}" role="img" aria-label="Working proxies over the last {DAYS} days">',
             f'<rect width="{WIDTH}" height="{HEIGHT}" rx="16" fill="{c["bg"]}"/>']
    last = points[-1][1] if points else {"total": 0, "by_type": {}}
    total = last.get("total", 0)
    parts += [f'<text x="28" y="58" fill="{c["muted"]}" font-size="14">Working right now</text>',
              f'<text x="26" y="112" fill="{c["text"]}" font-size="52" font-weight="600" letter-spacing="-1.5">'
              f'{_num(total)}</text>']
    for i, t in enumerate(PROXY_TYPES):
        y = 158 + i * 28
        n = last.get("by_type", {}).get(t, 0)
        parts += [f'<rect x="28" y="{y - 10}" width="10" height="10" rx="2" fill="{c[t]}"/>',
                  f'<text x="48" y="{y}" fill="{c["muted"]}" font-size="14">{t.upper()}</text>',
                  f'<text x="200" y="{y}" fill="{c["text"]}" font-size="14" text-anchor="end">{_num(n)}</text>']
    # the x axis covers the week, or less while the history is younger than that
    start = max(now - timedelta(days=DAYS), points[0][0]) if len(points) >= 2 else now - timedelta(days=DAYS)
    start = min(start, now - timedelta(hours=6))
    span = (now - start).total_seconds()

    def x_of(t: datetime) -> float:
        return left + (right - left) * (t - start).total_seconds() / span

    parts.append(f'<text x="28" y="{HEIGHT - 28}" fill="{c["muted"]}" font-size="12">checked every hour'
                 f'{f", last {DAYS} days" if span >= timedelta(days=DAYS).total_seconds() - 3600 else ""}</text>')
    parts.append(f'<line x1="{left}" y1="{bottom}" x2="{right}" y2="{bottom}" stroke="{c["line"]}" stroke-width="1"/>')
    midnight = start.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    while midnight < now:  # a line at the start of every day, labelled with the day
        x = x_of(midnight)
        parts.append(f'<line x1="{x:.1f}" y1="{top}" x2="{x:.1f}" y2="{bottom}" stroke="{c["line"]}"/>')
        if right - x > 40:
            parts.append(f'<text x="{x + 6:.1f}" y="{bottom + 22}" fill="{c["muted"]}" font-size="12">'
                         f'{escape(midnight.strftime("%a %d"))}</text>')
        midnight += timedelta(days=1)
    if len(points) >= 2:
        peak = max(r.get("total", 0) for _, r in points) or 1

        def y_of(v: float) -> float:
            return bottom - (bottom - top) * v / (peak * 1.08)

        below = [0.0] * len(points)
        for t in PROXY_TYPES:  # stacked: each protocol on top of the ones before it
            above = [b + (r.get("by_type", {}).get(t, 0) or 0) for b, (_, r) in zip(below, points)]
            upper = " ".join(f"{x_of(when):.1f},{y_of(v):.1f}" for (when, _), v in zip(points, above))
            lower = " ".join(f"{x_of(when):.1f},{y_of(v):.1f}" for (when, _), v in reversed(list(zip(points, below))))
            parts.append(f'<polygon points="{upper} {lower}" fill="{c[t]}" fill-opacity="0.85"/>')
            below = above
        parts.append(f'<text x="{right}" y="{top - 12}" fill="{c["muted"]}" font-size="12" text-anchor="end">'
                     f'peak {_num(peak)}</text>')
    else:
        parts.append(f'<text x="{(left + right) / 2:.0f}" y="{(top + bottom) / 2:.0f}" fill="{c["muted"]}" '
                     f'font-size="14" text-anchor="middle">The chart fills up with the next runs</text>')
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def countries_svg(countries: Dict[str, int], theme: str = "dark", limit: int = 10) -> str:
    """Where the working proxies are: the top countries as bars."""
    c = THEMES[theme]
    top = sorted(countries.items(), key=lambda kv: -kv[1])[:limit]
    row, pad = 24, 28
    height = pad * 2 + 22 + row * max(len(top), 1)
    most = max((n for _, n in top), default=1) or 1
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{height}" '
             f'viewBox="0 0 {WIDTH} {height}" '
             f'font-family="{FONT}" role="img" aria-label="Countries with the most working proxies">',
             f'<rect width="{WIDTH}" height="{height}" rx="16" fill="{c["bg"]}"/>',
             f'<text x="28" y="{pad + 10}" fill="{c["muted"]}" font-size="14">Where they are</text>']
    for i, (cc, n) in enumerate(top):
        y = pad + 36 + i * row
        width = (WIDTH - 250 - 90) * n / most
        name = COUNTRIES.get(cc, cc)
        name = name[4:] if name.startswith("the ") else name
        parts += [f'<text x="28" y="{y + 11}" fill="{c["text"]}" font-size="13">{escape(name)}</text>',
                  f'<rect x="250" y="{y}" width="{max(width, 2):.1f}" height="14" rx="3" fill="{c["socks5"]}"/>',
                  f'<text x="{250 + width + 10:.1f}" y="{y + 11}" fill="{c["muted"]}" font-size="12">{_num(n)}</text>']
    parts.append("</svg>")
    return "\n".join(parts) + "\n"
