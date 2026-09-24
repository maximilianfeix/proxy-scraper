"""Ergebnisdateien.

Jeder Lauf bekommt einen eigenen Ordner results/<datum>/ mit
  all.txt         typ://ip:port, schnellste zuerst (auch live während des Laufs)
  http.txt …      ip:port pro Protokoll – direkt für Tools, die nur eine Liste wollen
  proxies.json    alle Details (Latenz, Land, HTTPS, Anonymität, Exit-IP)
  proxies.csv     dasselbe als Tabelle
und results/latest.txt (bzw. der Symlink results/latest) zeigt immer auf den neuesten Lauf.
"""

from __future__ import annotations

import csv
import json
import os
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from .checker import CheckResult
from .parsing import PROXY_TYPES
from .paths import RESULTS_DIR, atomic_write


class ResultWriter:
    def __init__(self, run_dir: Optional[Path] = None, extra_file: Optional[Path] = None):
        self.run_dir = run_dir or RESULTS_DIR / f"{datetime.now():%Y-%m-%d_%H-%M-%S}"
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.extra_file = extra_file
        self.live_path = self.run_dir / "all.txt"
        self._live = self.live_path.open("w", encoding="utf-8")

    def add_live(self, r: CheckResult) -> None:
        self._live.write(f"{r.ptype}://{r.proxy}\n")
        self._live.flush()

    def finalize(self, results: Iterable[CheckResult]) -> Dict[str, Path]:
        self._live.close()
        rows = sorted(results, key=lambda r: r.latency)
        files: Dict[str, Path] = {}

        lines = "".join(f"{r.ptype}://{r.proxy}\n" for r in rows)
        self.live_path.write_text(lines, encoding="utf-8")
        files["Alle (typ://ip:port)"] = self.live_path
        for t in PROXY_TYPES:
            of_type = [r.proxy for r in rows if r.ptype == t]
            if of_type:
                path = self.run_dir / f"{t}.txt"
                path.write_text("\n".join(of_type) + "\n", encoding="utf-8")
                files[f"{t} (ip:port)"] = path

        json_path = self.run_dir / "proxies.json"
        json_path.write_text(json.dumps([_row(r) for r in rows], indent=1, ensure_ascii=False), encoding="utf-8")
        files["Details (JSON)"] = json_path

        csv_path = self.run_dir / "proxies.csv"
        with csv_path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(_row(rows[0]).keys()) if rows else ["proxy"])
            writer.writeheader()
            writer.writerows(_row(r) for r in rows)
        files["Details (CSV)"] = csv_path

        if self.extra_file:
            self.extra_file.parent.mkdir(parents=True, exist_ok=True)
            self.extra_file.write_text(lines, encoding="utf-8")
            files["Zusatzdatei (-o)"] = self.extra_file

        _point_latest(self.run_dir)
        return files


def _row(r: CheckResult) -> dict:
    d = asdict(r)
    d.pop("key")
    d["url"] = f"{r.ptype}://{r.proxy}"
    return d


LATEST_POINTER = "latest.txt"


def _point_latest(run_dir: Path) -> None:
    """results/latest.txt nennt immer den neuesten Lauf; results/latest ist zusätzlich ein Symlink.

    Der Symlink ist bequem zum Reinschauen, braucht unter Windows aber Admin- oder
    Entwicklerrechte – die Zeigerdatei funktioniert überall.
    """
    atomic_write(run_dir.parent / LATEST_POINTER, run_dir.name + "\n")
    latest = run_dir.parent / "latest"
    try:
        if latest.is_symlink():
            latest.unlink()
        if not latest.exists():
            os.symlink(run_dir.name, latest, target_is_directory=True)
    except OSError:
        pass  # keine Symlinks erlaubt – latest.txt reicht


def latest_run_dir(results_dir: Path = RESULTS_DIR) -> Optional[Path]:
    pointer = results_dir / LATEST_POINTER
    try:
        name = pointer.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):  # fehlt, keine Rechte oder kaputt -> Symlink versuchen
        name = ""
    if name:
        # Nur ein Ordnername direkt unter results/ – leer, "..", oder Pfade wie "a/../.." würden
        # sonst auf results/ selbst oder außerhalb zeigen
        if name not in (".", "..") and Path(name).name == name:
            run_dir = results_dir / name
            if run_dir.is_dir():
                return run_dir
    link = results_dir / "latest"
    return link if link.is_dir() else None  # Läufe aus älteren Versionen ohne latest.txt


def has_latest_results(results_dir: Path = RESULTS_DIR) -> bool:
    """Gibt es einen letzten Lauf mit Treffern? Liest dafür nicht die ganze Datei."""
    run_dir = latest_run_dir(results_dir)
    try:
        return run_dir is not None and (run_dir / "all.txt").stat().st_size > 0
    except OSError:
        return False


def latest_results(results_dir: Path = RESULTS_DIR) -> List[str]:
    """Proxys des letzten Laufs für --recheck ohne Datei."""
    run_dir = latest_run_dir(results_dir)
    path = run_dir / "all.txt" if run_dir else None
    return path.read_text(encoding="utf-8").splitlines() if path and path.exists() else []
