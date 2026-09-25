#!/usr/bin/env python3
"""Render the README banner (docs/banner-dark.svg, docs/banner-light.svg) and the logo (docs/logo.svg).

Same look as the website: the logo is a route through a proxy node that forms a check mark,
and the banner shows that route through the five checks every proxy has to pass.
"""

# ruff: noqa: E501  (SVG markup reads better unwrapped)

from html import escape
from pathlib import Path

DOCS = Path(__file__).resolve().parent

SIGNAL, INK = "#D4F77A", "#121113"
THEMES = {
    "dark": {"bg": "#121113", "line": "#2B292F", "text": "#EDEBE6", "muted": "#9A97A0", "route": SIGNAL},
    "light": {"bg": "#EFEFEC", "line": "#DAD9D4", "text": "#121113", "muted": "#5F5C66", "route": "#3F5A00"},
}

# 64×64: source → proxy node → target, together a check mark
MARK = f"""<rect width="64" height="64" rx="18" fill="{SIGNAL}"/>
    <path d="M13 31.5 26.5 44.5 51 18" fill="none" stroke="{INK}" stroke-width="5.5" stroke-linecap="round" stroke-linejoin="round"/>
    <circle cx="13" cy="31.5" r="4.6" fill="{INK}"/><circle cx="51" cy="18" r="4.6" fill="{INK}"/>
    <circle cx="26.5" cy="44.5" r="7.6" fill="{SIGNAL}" stroke="{INK}" stroke-width="5"/>"""

GATES = [("Lists", 700, 250), ("Handshake", 820, 170), ("Honeypots", 950, 262), ("Content", 1070, 176), ("Details", 1190, 232)]


def smooth(points) -> str:
    """Smooth curve exactly through every point (Catmull-Rom as cubic Bézier pieces)."""
    d = f"M{points[0][0]} {points[0][1]}"
    for i in range(1, len(points)):
        x0, y0 = points[i - 2] if i > 1 else points[i - 1]
        x1, y1 = points[i - 1]
        x2, y2 = points[i]
        x3, y3 = points[i + 1] if i + 1 < len(points) else points[i]
        d += f" C {x1 + (x2 - x0) / 6:.1f} {y1 + (y2 - y0) / 6:.1f} {x2 - (x3 - x1) / 6:.1f} {y2 - (y3 - y1) / 6:.1f} {x2} {y2}"
    return d


ROUTE = smooth([(640, 262), *((x, y) for _, x, y in GATES), (1230, 214)])
SANS = "'Geist', 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif"


def logo() -> str:
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64" role="img" aria-label="proxy-scraper">
  {MARK}
</svg>
"""


def render(c: dict) -> str:
    gates = []
    for i, (label, x, y) in enumerate(GATES):
        above = i % 2 == 1
        gates.append(f"""
    <g class="gate" style="animation-delay:{0.35 + 0.18 * i:.2f}s">
      <circle cx="{x}" cy="{y}" r="10" fill="{SIGNAL}" stroke="{c["route"]}" stroke-width="2"/>
      <text x="{x}" y="{y - 22 if above else y + 34}" text-anchor="middle" fill="{c["muted"]}" font-family="{SANS}" font-size="15">{escape(label)}</text>
    </g>""")
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 360" width="1280" height="360" role="img" aria-label="proxy-scraper – free proxies that actually work. Every proxy passes five checks: lists, handshake, honeypots, content and details.">
  <style>
    .fade {{ animation: fade .8s cubic-bezier(.16,1,.3,1) both; }}
    .route {{ stroke-dasharray: 100; stroke-dashoffset: 100; animation: draw 1.6s cubic-bezier(.16,1,.3,1) .2s forwards; }}
    .gate {{ animation: fade .6s cubic-bezier(.16,1,.3,1) both; }}
    @keyframes fade {{ from {{ opacity: 0; transform: translateY(8px); }} to {{ opacity: 1; transform: none; }} }}
    @keyframes draw {{ to {{ stroke-dashoffset: 0; }} }}
    @media (prefers-reduced-motion: reduce) {{ .fade, .gate {{ animation: none; }} .route {{ animation: none; stroke-dashoffset: 0; }} }}
  </style>
  <defs><clipPath id="frame"><rect width="1280" height="360" rx="24"/></clipPath></defs>
  <g clip-path="url(#frame)"><rect width="1280" height="360" fill="{c["bg"]}"/></g>

  <g class="fade">
    <svg x="72" y="70" width="56" height="56" viewBox="0 0 64 64">{MARK}</svg>
    <text x="144" y="110" fill="{c["text"]}" font-family="{SANS}" font-size="30" font-weight="600" letter-spacing="-1">proxy-scraper</text>
    <text x="70" y="206" fill="{c["text"]}" font-family="{SANS}" font-size="66" font-weight="600" letter-spacing="-3.4">Free proxies that</text>
    <text x="70" y="270" fill="{c["text"]}" font-family="{SANS}" font-size="66" font-weight="600" letter-spacing="-3.4">actually work.</text>
    <text x="72" y="312" fill="{c["muted"]}" font-family="{SANS}" font-size="17">700+ sources, five checks, a fresh list every 6 hours.</text>
  </g>

  <path d="{ROUTE}" fill="none" stroke="{c["line"]}" stroke-width="2"/>
  <path class="route" pathLength="100" d="{ROUTE}" fill="none" stroke="{c["route"]}" stroke-width="3" stroke-linecap="round"/>
  {"".join(gates)}
</svg>
"""


def main() -> None:
    for name, colors in THEMES.items():
        (DOCS / f"banner-{name}.svg").write_text(render(colors), encoding="utf-8")
    (DOCS / "logo.svg").write_text(logo(), encoding="utf-8")


if __name__ == "__main__":
    main()
