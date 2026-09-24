"""Ablageorte.

- Quellenliste: im Paket (proxyscraper/sources.json)
- aus einem geklonten Repo: gelernter Zustand in data/, Ergebnisse in results/ – beides im Projekt
- installiert (pip/pipx): gelernter Zustand im Benutzerordner des Systems, Ergebnisse im aktuellen Ordner
- PROXY_SCRAPER_HOME überschreibt den Ordner für den gelernten Zustand
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = PACKAGE_DIR.parent
APP_NAME = "proxy-scraper"


def is_checkout(project_dir: Path = PROJECT_DIR) -> bool:
    """Läuft das Programm direkt aus dem Repo (statt aus einer Installation)?"""
    return (project_dir / "pyproject.toml").is_file() and (project_dir / "proxy_scraper.py").is_file()


def user_data_dir(platform: str = sys.platform, env=os.environ, home: Optional[Path] = None) -> Path:
    """Üblicher Ordner für Anwendungsdaten des jeweiligen Systems."""
    home = home or Path.home()
    if platform == "darwin":
        return home / "Library" / "Application Support" / APP_NAME
    if platform == "win32":
        return Path(env.get("LOCALAPPDATA") or home / "AppData" / "Local") / APP_NAME
    return Path(env.get("XDG_DATA_HOME") or home / ".local" / "share") / APP_NAME


def data_dir(env=os.environ) -> Path:
    if env.get("PROXY_SCRAPER_HOME"):
        return Path(env["PROXY_SCRAPER_HOME"]).expanduser()
    return PROJECT_DIR / "data" if is_checkout() else user_data_dir(env=env)


def results_dir() -> Path:
    return PROJECT_DIR / "results" if is_checkout() else Path.cwd() / "results"


DATA_DIR = data_dir()
RESULTS_DIR = results_dir()


def atomic_write(path: Path, text: str) -> None:
    # Erst temporär schreiben, dann umbenennen – ein Abbruch hinterlässt keine halbe Datei
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)
