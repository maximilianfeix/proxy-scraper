"""Bereitet die Treffer eines Laufs für den Branch `proxy-list` auf (läuft in GitHub Actions).

    python -m proxyscraper.publish results/<lauf> public/ --min 20

Schreibt Listen pro Protokoll, HTTPS- und Elite-Listen, JSON/CSV, Badge-Dateien für shields.io
und eine README. Gibt es weniger als `--min` Treffer (z. B. weil der Runner gerade kein Glück
hatte), endet es mit Code 78 und schreibt nichts – die alte Liste bleibt dann online.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import statistics
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from .parsing import PROXY_TYPES

SKIP_EXIT_CODE = 78
RAW_BASE = "https://raw.githubusercontent.com/maximilianfeix/proxy-scraper/proxy-list"


def load_rows(run_dir: Path) -> List[dict]:
    rows = json.loads((run_dir / "proxies.json").read_text(encoding="utf-8"))
    return sorted(rows, key=lambda r: r["latency"])


def num(n: int) -> str:
    """Tausenderpunkte: 12345 -> 12.345"""
    return f"{n:,}".replace(",", ".")


def badge(label: str, count: int, color: str) -> dict:
    """Format für https://shields.io/badges/endpoint-badge"""
    return {"schemaVersion": 1, "label": label, "message": num(count), "color": color}


def stats_for(rows: List[dict], now: datetime) -> dict:
    return {
        "updated": now.isoformat(timespec="seconds"),
        "total": len(rows),
        "by_type": {t: sum(1 for r in rows if r["ptype"] == t) for t in PROXY_TYPES},
        "https": sum(1 for r in rows if r.get("https")),
        "elite": sum(1 for r in rows if r.get("anonymity") == "elite"),
        "countries": dict(Counter(r["country"] for r in rows if r.get("country")).most_common(15)),
        "median_latency": round(statistics.median(r["latency"] for r in rows)) if rows else 0,
    }


def write_lists(rows: List[dict], out: Path) -> Dict[str, int]:
    files = {
        "all.txt": [r["url"] for r in rows],
        "https.txt": [r["url"] for r in rows if r.get("https")],
        "elite.txt": [r["url"] for r in rows if r.get("anonymity") == "elite"],
    }
    for t in PROXY_TYPES:
        files[f"{t}.txt"] = [r["proxy"] for r in rows if r["ptype"] == t]
    for name, lines in files.items():
        (out / name).write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")
    return {name: len(lines) for name, lines in files.items()}


def readme(stats: dict, counts: Dict[str, int]) -> str:
    updated = datetime.fromisoformat(stats["updated"]).strftime("%d.%m.%Y %H:%M UTC")
    rows = [
        ("Alle (`typ://ip:port`)", "all.txt"),
        ("HTTP (`ip:port`)", "http.txt"),
        ("SOCKS4 (`ip:port`)", "socks4.txt"),
        ("SOCKS5 (`ip:port`)", "socks5.txt"),
        ("HTTPS-fähig (`typ://ip:port`)", "https.txt"),
        ("Elite (`typ://ip:port`)", "elite.txt"),
    ]
    table = "\n".join(f"| {label} | {num(counts[name])} | [{name}]({RAW_BASE}/{name}) |" for label, name in rows)
    details = f"[proxies.json]({RAW_BASE}/proxies.json) · [proxies.csv]({RAW_BASE}/proxies.csv)"
    countries = " · ".join(f"{cc} {num(n)}" for cc, n in stats["countries"].items()) or "–"
    return f"""# Live-Proxyliste

Automatisch erzeugt von [proxy-scraper](https://github.com/maximilianfeix/proxy-scraper) über GitHub Actions.
Jeder Proxy hier hat beim letzten Lauf wirklich funktioniert – sortiert nach Latenz, schnellste zuerst.

**Stand:** {updated} · **{num(stats["total"])} Proxys** · Median-Latenz {num(stats["median_latency"])} ms

| Liste | Anzahl | Datei |
|---|---:|---|
{table}
| Details (Latenz, Land, HTTPS, Anonymität) | {num(stats["total"])} | {details} |

**Häufigste Länder:** {countries}

> Öffentliche Proxys werden von Unbekannten betrieben. Keine Passwörter oder persönlichen Daten darüber schicken.
"""


def step_summary(stats: dict) -> str:
    by_type = " · ".join(f"{t}: {n}" for t, n in stats["by_type"].items())
    return (f"### Proxy-Liste aktualisiert\n\n**{stats['total']}** funktionierende Proxys ({by_type}), "
            f"{stats['https']} HTTPS-fähig, {stats['elite']} Elite, Median-Latenz {stats['median_latency']} ms\n")


def write_json(path: Path, data, indent: Optional[int] = None) -> None:
    path.write_text(json.dumps(data, indent=indent, ensure_ascii=False), encoding="utf-8")


def publish(run_dir: Path, out: Path, minimum: int = 20, now: Optional[datetime] = None) -> int:
    rows = load_rows(run_dir)
    if len(rows) < minimum:
        print(f"Nur {len(rows)} Treffer (< {minimum}) – alte Liste bleibt online.")
        return SKIP_EXIT_CODE
    now = now or datetime.now(timezone.utc)
    out.mkdir(parents=True, exist_ok=True)
    counts = write_lists(rows, out)
    for name in ("proxies.json", "proxies.csv"):
        shutil.copyfile(run_dir / name, out / name)
    stats = stats_for(rows, now)
    write_json(out / "stats.json", stats, indent=1)
    badges = out / "badges"
    badges.mkdir(exist_ok=True)
    colors = {"total": "brightgreen", "http": "blue", "socks4": "blueviolet", "socks5": "green"}
    write_json(badges / "total.json", badge("working proxies", stats["total"], colors["total"]))
    for t in PROXY_TYPES:
        write_json(badges / f"{t}.json", badge(t, stats["by_type"][t], colors[t]))
    write_json(badges / "updated.json", {"schemaVersion": 1, "label": "updated",
                                         "message": now.strftime("%Y-%m-%d %H:%M UTC"), "color": "grey"})
    (out / "README.md").write_text(readme(stats, counts), encoding="utf-8")

    summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_file:
        with open(summary_file, "a", encoding="utf-8") as fh:
            fh.write(step_summary(stats))
    print(f"{stats['total']} Proxys nach {out} geschrieben.")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Treffer eines Laufs für den Branch proxy-list aufbereiten")
    p.add_argument("run_dir", type=Path)
    p.add_argument("out_dir", type=Path)
    p.add_argument("--min", type=int, default=20, help="mindestens so viele Treffer, sonst nichts schreiben")
    args = p.parse_args(argv)
    return publish(args.run_dir, args.out_dir, args.min)


if __name__ == "__main__":
    sys.exit(main())
