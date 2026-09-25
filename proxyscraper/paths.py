"""Where things are stored.

- source list: in the package (proxyscraper/sources.json)
- from a cloned repo: learned state in data/, results in results/ – both inside the project
- installed (pip/pipx): learned state in the system's user data folder, results in the current folder
- PROXY_SCRAPER_HOME overrides the folder for the learned state
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
    """Is the program running straight from the repo (instead of an installation)?"""
    return (project_dir / "pyproject.toml").is_file() and (project_dir / "proxy_scraper.py").is_file()


def user_data_dir(platform: str = sys.platform, env=os.environ, home: Optional[Path] = None) -> Path:
    """The usual folder for application data on this system."""
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
    # write to a temporary file first, then rename – an interruption leaves no half-written file
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)
