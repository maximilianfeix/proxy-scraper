"""Erzeugt die Bilder für die README aus echten Programmansichten.

    python3 docs/make_demo.py

- docs/demo.svg       animiert: Einrichtungsassistent → Sammeln → Live-Dashboard → Bericht
- docs/wizard.svg     Einrichtungsassistent
- docs/dashboard.svg  Live-Dashboard
- docs/summary.svg    Abschlussbericht

Alle Daten sind Beispiele; IP-Adressen stammen aus den Dokumentationsbereichen (RFC 5737).
Flaggen-Emojis werden durch Ländercodes ersetzt, weil SVG-Schriften sie nicht darstellen.
"""

from __future__ import annotations

import io
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from rich.console import Console, Group  # noqa: E402
from rich.terminal_theme import MONOKAI  # noqa: E402
from rich.text import Text  # noqa: E402

from proxyscraper.checker import CheckResult  # noqa: E402
from proxyscraper.options import RunOptions  # noqa: E402
from proxyscraper.ui import dashboard, report, widgets  # noqa: E402
from proxyscraper.ui import wizard as wizard_module  # noqa: E402

DOCS = ROOT / "docs"
WIDTH = 104
TITLE = "proxy-scraper"
SECONDS_PER_FRAME = 3.2

NETS = ("192.0.2", "198.51.100", "203.0.113")
COUNTRIES = (("US", 30), ("DE", 14), ("BR", 12), ("ID", 10), ("FR", 9), ("NL", 8), ("SG", 6), ("JP", 5))
PORTS = {"http": (80, 3128, 8080, 8888), "socks4": (4145, 1080), "socks5": (1080, 10808, 9050)}


def country_code_only(cc: str) -> Text:
    return Text(cc or "··", style="bold bright_white" if cc else "grey50")


dashboard.country_cell = country_code_only
report.country_cell = country_code_only
wizard_module.flag = lambda cc: ""


def ip(rng: random.Random) -> str:
    return f"{rng.choice(NETS)}.{rng.randint(1, 254)}"


def live_stats(seed: int, checked_total: int, found: int, elapsed: float) -> dashboard.LiveStats:
    rng = random.Random(seed)
    s = dashboard.LiveStats({"http": 520_000, "socks4": 210_000, "socks5": 327_000})
    s.start -= elapsed
    for _ in range(60):
        s.speed.append(rng.uniform(2900, 4100))
    share = {"http": 0.49, "socks4": 0.18, "socks5": 0.33}
    for t, part in share.items():
        s.checked_by_type[t] = int(checked_total * part)
    s.checked = sum(s.checked_by_type.values())
    codes = [c for c, _ in COUNTRIES]
    weights = [w for _, w in COUNTRIES]
    for i in range(found):
        t = rng.choices(("http", "socks4", "socks5"), (5, 2, 3))[0]
        latency = int(min(rng.lognormvariate(6.9, 0.75), 7900))
        anonymity = "elite" if t != "http" else rng.choices(("elite", "anonymous", "transparent"), (5, 3, 1))[0]
        r = CheckResult(f"{t} x{i}", t, f"{ip(rng)}:{rng.choice(PORTS[t])}", latency, ip(rng),
                        rng.random() < 0.46, anonymity, rng.choices(codes, weights)[0])
        s.add_working(r)
        s.add_details(r)
        s.countries[r.country] += 1
    s.results = list(s.recent)  # nur für die Demo
    return s


def check_view(seed: int, checked: int, found: int, elapsed: float, passing: int) -> dashboard.CheckDashboard:
    s = live_stats(seed, checked, found, elapsed)
    s.passing = passing
    view = dashboard.CheckDashboard(s, Path("results/2026-09-24_18-42-07/all.txt"), 2000, True,
                                    "nur HTTPS · mind. anonymous · ≤ 3000 ms", 50)
    clock = [1000.0]
    view.progress.get_time = lambda: clock[0]
    view.progress.update(view.task, completed=max(checked - 35_000, 0))
    clock[0] += 10
    view.progress.update(view.task, completed=checked)
    return view


def collect_view() -> dashboard.CollectView:
    import time

    view = dashboard.CollectView(726, time.perf_counter() - 14)
    view.ok, view.failed, view.bytes, view.unique = 402, 21, 188 * 2**20, 781_442
    view.progress.update(view.task, completed=423)
    return view


def wizard_frames():
    w = wizard_module.Wizard(RunOptions(), last=RunOptions(types=["socks5"], want=50), can_recheck=True)
    w.handle("down")
    start = Group(widgets.banner(), w.__rich__())
    w.handle("enter")
    summary = Group(widgets.banner(), w.__rich__())
    return start, summary


def summary_frame(seed: int):
    s = live_stats(seed, 289_000, 2847, 287)
    rows = [r for r in s.recent]
    rng = random.Random(seed + 1)
    kept = [CheckResult(f"x{i}", t, f"{NETS[i % 3]}.{20 + i}:{rng.choice(PORTS[t])}", 90 + i * 23, ip(rng), True,
                        "elite" if t != "http" else "anonymous", rng.choice(("US", "DE", "NL", "JP", "SG")))
            for i, t in enumerate(rng.choices(("http", "socks5", "socks4"), (4, 5, 1), k=40))]
    best = [
        (0.184, 92, 500, "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt"),
        (0.121, 61, 504, "https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/protocols/socks5/data.txt"),
        (0.087, 44, 506, "https://raw.githubusercontent.com/iplocate/free-proxy-list/main/protocols/socks5.txt"),
    ]
    files = {label: Path(f"results/2026-09-24_18-42-07/{name}") for label, name in (
        ("Alle (typ://ip:port)", "all.txt"), ("http (ip:port)", "http.txt"),
        ("socks5 (ip:port)", "socks5.txt"), ("Details (JSON)", "proxies.json"))}
    return s, rows, kept, best, files


def setup_view() -> None:
    """Vorbereitung wie im echten Lauf (Beispielwerte)."""
    widgets.console.print(widgets.banner())
    widgets.section("Vorbereitung")
    for label, value in (
        ("Deine IP", "203.0.113.7"),
        ("Prüfziel", "checkip.amazonaws.com  ·  Bestätigung über httpbin.org"),
        ("Modus", "mit HTTPS-Test · Länder · Filter: nur HTTPS · stoppt bei 50 Treffern"),
        ("Quellen", "726 aktiv  (328 kuratiert · 238 aus 5/5 Meta-Listen · 540 entdeckt)"),
        ("Gesammelt", "1.018.830 einzigartige Proxys aus 501/501 Quellen  (162 MB in 28 s)"),
        ("Verlauf", "644 früher funktionierende Proxys werden zuerst geprüft"),
    ):
        widgets.info(label, value)
    widgets.section_end()


NEXT_STEPS = (
    ("Schnellsten testen", "curl -x socks5h://198.51.100.20:1080 https://api.ipify.org"),
    ("Als Proxy-Server", "proxy-scraper --recheck --serve"),
    ("Später neu prüfen", "proxy-scraper --recheck"),
)


def render(renderable=None, printer=None, lines: int = 0) -> str:
    """Rendert in eine aufzeichnende Konsole und gibt das SVG zurück (optional auf feste Zeilenzahl)."""
    console = Console(width=WIDTH, record=True, force_terminal=True, color_system="truecolor", file=io.StringIO())
    widgets.console = console
    if printer:
        printer()
    else:
        console.print(renderable)
    used = console.export_text(clear=False).count("\n")
    for _ in range(max(lines - used, 0)):
        console.print()
    return console.export_svg(title=TITLE, theme=MONOKAI)


def count_lines(renderable=None, printer=None) -> int:
    console = Console(width=WIDTH, record=True, force_terminal=True, file=io.StringIO())
    widgets.console = console
    printer() if printer else console.print(renderable)
    return console.export_text().count("\n")


def animate(frames: list) -> str:
    """Mehrere rich-SVGs zu einem animierten SVG kombinieren (reines CSS, läuft auf GitHub)."""
    view_box = re.search(r'viewBox="([^"]+)"', frames[0]).group(1)
    n = len(frames)
    duration = n * SECONDS_PER_FRAME
    visible = 100 / n
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{view_box}">',
        "<style>",
        f".frame {{ opacity: 0; animation: show {duration:.1f}s infinite; }}",
        f"@keyframes show {{ 0% {{ opacity: 1; }} {visible:.3f}% {{ opacity: 1; }} "
        f"{visible + 0.01:.3f}% {{ opacity: 0; }} 100% {{ opacity: 0; }} }}",
        "</style>",
    ]
    for i, frame in enumerate(frames):
        inner = re.sub(r"^<svg[^>]*>", f'<svg viewBox="{view_box}">', frame.strip(), count=1)
        parts.append(f'<g class="frame" style="animation-delay: {i * SECONDS_PER_FRAME:.1f}s">{inner}</g>')
    parts.append("</svg>")
    return "\n".join(parts)


def main() -> None:
    start, wizard_summary = wizard_frames()
    early = check_view(3, 41_000, 312, 36, 9)
    late = check_view(7, 289_000, 2847, 287, 38)
    s, rows, kept, best, files = summary_frame(11)

    def print_summary():
        report.render_summary(s, rows, kept[:12], best, files, True, "nur HTTPS · mind. anonymous", NEXT_STEPS)

    views = [
        {"renderable": start},
        {"renderable": wizard_summary},
        {"printer": setup_view},
        {"renderable": Group(widgets.banner(), collect_view())},
        {"renderable": early},
        {"renderable": late},
        {"printer": lambda: report.render_summary(s, rows, kept[:5], best[:2], {}, True, "nur HTTPS", NEXT_STEPS[:2])},
    ]
    # Alle Frames auf die Höhe der größten Ansicht bringen, damit das Bild beim Wechsel nicht springt
    lines = max(count_lines(**view) for view in views)
    frames = [render(lines=lines, **view) for view in views]
    (DOCS / "demo.svg").write_text(animate(frames), encoding="utf-8")
    (DOCS / "wizard.svg").write_text(render(start), encoding="utf-8")
    (DOCS / "dashboard.svg").write_text(render(late), encoding="utf-8")
    (DOCS / "summary.svg").write_text(render(printer=print_summary), encoding="utf-8")
    print("docs/demo.svg, wizard.svg, dashboard.svg, summary.svg geschrieben")


if __name__ == "__main__":
    main()
