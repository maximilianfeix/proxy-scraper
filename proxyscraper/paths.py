"""Where things are stored.

- source list: in the package (proxyscraper/sources.json)
- from a cloned repo: learned state in data/, results in results/ – both inside the project
- installed (pip/pipx): learned state in the system's user data folder, results in the current folder
- PROXY_SCRAPER_HOME overrides the folder for the learned state
"""

from __future__ import annotations

import contextlib
import os
import secrets
import sys
import time
from pathlib import Path
from typing import BinaryIO, Iterator, Optional

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
    """Replace `path` with `text` in one step – an interruption leaves no half-written file."""
    with atomic_writer(path) as fh:
        fh.write(text.encode("utf-8"))


def atomic_write_bytes(path: Path, data: bytes) -> None:
    with atomic_writer(path) as fh:
        fh.write(data)


@contextlib.contextmanager
def atomic_writer(path: Path) -> Iterator[BinaryIO]:
    """Binary file handle whose content replaces `path` once the block ends without an error.

    Every writer gets its own temporary file next to the target, so overlapping writers (threads, or a CLI
    run and the MCP server sharing the data folder) never collide: each rename is atomic and the target is
    always one complete version. That is not a merge – with two writers of the same state file the last one
    wins (see "State files" in docs/ARCHITECTURE.md). On any error the temporary file is removed again."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = _create_temp(path)
    try:
        with os.fdopen(fd, "wb") as fh:
            yield fh
            fh.flush()
            os.fsync(fh.fileno())
        _replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def _create_temp(path: Path) -> tuple[int, str]:
    # Like mkstemp, but with mode 0666 so the OS applies the umask in effect now (mkstemp forces 0600)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    for _ in range(100):
        tmp = str(path.parent / f".{path.name}.{secrets.token_hex(4)}.tmp")
        try:
            return os.open(tmp, flags, 0o666), tmp
        except FileExistsError:
            continue
    raise FileExistsError(f"no free temporary name next to {path}")


def _replace(src: str, dst: Path, attempts: int = 5) -> None:
    for attempt in range(attempts):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            # Windows: the target is briefly open in another process (a reader, or another writer's rename) –
            # wait a moment instead of failing. Elsewhere a PermissionError is final.
            if os.name != "nt" or attempt == attempts - 1:
                raise
            time.sleep(0.05 * (attempt + 1))
