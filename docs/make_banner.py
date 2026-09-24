#!/usr/bin/env python3
"""Render the README banner (docs/banner-dark.svg, docs/banner-light.svg)."""

# ruff: noqa: E501  (SVG markup reads better unwrapped)

from html import escape
from pathlib import Path

DOCS = Path(__file__).resolve().parent

THEMES = {
    "dark": dict(bg1="#0B1622", bg2="#0F2233", grid="#16293B", glow="#38BDF8", text="#E6EDF3", muted="#8BA3B8",
                 faint="#5E7B94", accent="#38BDF8", accent2="#34D399", bar="#132638", border="#24405A"),
    "light": dict(bg1="#F6F9FC", bg2="#EAF2F8", grid="#DCE7F0", glow="#0284C7", text="#10243A", muted="#43647E",
                  faint="#6B879E", accent="#0284C7", accent2="#10B981", bar="#FFFFFF", border="#D3E1EC"),
}

# funnel: label, detail, bar width
STAGES = [
    ("700+ sources", "lists · APIs · GitHub discovery", 440),
    ("~1M candidates", "parsed on all cores", 360),
    ("checked & confirmed", "two sites · same exit IP", 280),
    ("verified proxies", "HTTPS · anonymity · country", 200),
]

MONO = "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"
SANS = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif"


def render(c: dict) -> str:
    x0, y0 = 760, 70
    bars = []
    for i, (label, detail, width) in enumerate(STAGES):
        y = y0 + i * 58
        x = x0 + (440 - width) / 2
        last = i == len(STAGES) - 1
        fill = "url(#accent)" if last else c["bar"]
        label_color = "#FFFFFF" if last else c["text"]
        bars.append(f"""
    <g class="grow" style="animation-delay:{0.2 + 0.15 * i:.2f}s">
      <rect x="{x:.0f}" y="{y}" width="{width}" height="44" rx="10" fill="{fill}" stroke="{c["border"] if not last else "none"}"/>
      <text x="{x0 + 220}" y="{y + 20}" text-anchor="middle" fill="{label_color}" font-family="{MONO}" font-size="15" font-weight="700">{escape(label)}</text>
      <text x="{x0 + 220}" y="{y + 36}" text-anchor="middle" fill="{label_color if last else c["faint"]}" fill-opacity="{0.85 if last else 1}" font-family="{MONO}" font-size="11">{escape(detail)}</text>
    </g>""")
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 360" width="1280" height="360" role="img" aria-label="proxy-scraper – free proxies that actually work. 700+ sources, about a million candidates, checked and confirmed, verified proxies.">
  <style>
    .grow, .fade {{ animation: fade .7s ease-out both; }}
    .bolt {{ animation: glow 3s ease-in-out infinite; }}
    @keyframes fade {{ from {{ opacity: 0; transform: translateY(8px); }} to {{ opacity: 1; transform: none; }} }}
    @keyframes glow {{ 0%, 100% {{ opacity: 1; }} 50% {{ opacity: .7; }} }}
    @media (prefers-reduced-motion: reduce) {{ .grow, .fade, .bolt {{ animation: none; }} }}
  </style>
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="{c["bg1"]}"/><stop offset="1" stop-color="{c["bg2"]}"/>
    </linearGradient>
    <radialGradient id="glow" cx="0.8" cy="0.5" r="0.55">
      <stop offset="0" stop-color="{c["glow"]}" stop-opacity=".14"/><stop offset="1" stop-color="{c["glow"]}" stop-opacity="0"/>
    </radialGradient>
    <linearGradient id="accent" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="{c["accent"]}"/><stop offset="1" stop-color="{c["accent2"]}"/>
    </linearGradient>
    <pattern id="grid" width="32" height="32" patternUnits="userSpaceOnUse">
      <path d="M32 0H0V32" fill="none" stroke="{c["grid"]}"/>
    </pattern>
    <clipPath id="frame"><rect width="1280" height="360" rx="20"/></clipPath>
  </defs>
  <g clip-path="url(#frame)">
    <rect width="1280" height="360" fill="url(#bg)"/>
    <rect width="1280" height="360" fill="url(#grid)" opacity=".5"/>
    <rect width="1280" height="360" fill="url(#glow)"/>
  </g>

  <g class="fade">
    <rect x="72" y="92" width="76" height="76" rx="20" fill="url(#accent)"/>
    <path class="bolt" d="M116 104 L94 138 H110 L104 158 L128 122 H112 Z" fill="#FFFFFF"/>
    <text x="168" y="148" fill="{c["text"]}" font-family="{MONO}" font-size="54" font-weight="800" letter-spacing="-1">proxy-scraper</text>
    <text x="74" y="222" fill="{c["text"]}" font-family="{SANS}" font-size="28" font-weight="600">Free proxies that actually work.</text>
    <text x="74" y="258" fill="{c["muted"]}" font-family="{SANS}" font-size="18">Scraped from hundreds of sources, verified for real, smarter with every run.</text>
    <text x="74" y="300" fill="{c["faint"]}" font-family="{MONO}" font-size="14">$ pipx install git+https://github.com/maximilianfeix/proxy-scraper.git</text>
  </g>
  {"".join(bars)}
</svg>
"""


def main() -> None:
    for name, colors in THEMES.items():
        (DOCS / f"banner-{name}.svg").write_text(render(colors), encoding="utf-8")


if __name__ == "__main__":
    main()
