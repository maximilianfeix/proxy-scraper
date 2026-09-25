"""Result files.

Every run gets its own folder results/<date>/ with
  all.txt         type://ip:port, fastest first (also live during the run)
  http.txt …      ip:port per protocol – ready for tools that just want a list
  proxies.json    every detail (latency, country, HTTPS, anonymity, exit IP)
  proxies.csv     the same as a table
and results/latest.txt (or the symlink results/latest) always points to the newest run.
"""

from __future__ import annotations

import contextlib
import csv
import json
import os
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, TextIO

from .checker import CheckResult
from .exporters import EXPORTERS
from .parsing import PROXY_TYPES
from .paths import RESULTS_DIR, atomic_write
from .targets import target_label


def new_run_dir(base: Path) -> Path:
    """Folder with a timestamp; two runs in the same second get -2, -3 … instead of overwriting each other."""
    stamp = f"{datetime.now():%Y-%m-%d_%H-%M-%S}"
    base.mkdir(parents=True, exist_ok=True)
    for n in range(1, 1000):
        path = base / (stamp if n == 1 else f"{stamp}-{n}")
        try:
            path.mkdir()
        except FileExistsError:
            continue
        return path
    raise FileExistsError(f"too many runs in one second: {stamp}")


class ResultWriter:
    def __init__(self, run_dir: Optional[Path] = None, extra_file: Optional[Path] = None,
                 exports: Sequence[str] = (), stdout: Optional[TextIO] = None):
        self.run_dir = run_dir or new_run_dir(RESULTS_DIR)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.extra_file = extra_file
        self.stdout = stdout  # -o -: the hits also go here, one type://ip:port per line
        self.exports = list(exports)
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
        files["All (type://ip:port)"] = self.live_path
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
            writer = csv.DictWriter(fh, fieldnames=list(_csv_row(rows[0]).keys()) if rows else ["proxy"])
            writer.writeheader()
            writer.writerows(_csv_row(r) for r in rows)
        files["Details (CSV)"] = csv_path

        now = datetime.now()
        for name in self.exports:
            filename, render = EXPORTERS[name]
            path = self.run_dir / filename
            path.write_text(render(rows, now), encoding="utf-8")
            files[f"{name} ({filename})"] = path

        if self.extra_file:
            self.extra_file.parent.mkdir(parents=True, exist_ok=True)
            self.extra_file.write_text(lines, encoding="utf-8")
            files["Extra file (-o)"] = self.extra_file
        if self.stdout is not None:
            try:
                self.stdout.write(lines)
                self.stdout.flush()
            except OSError:  # `| head` stopped reading early – BrokenPipeError, on Windows EINVAL
                _silence(self.stdout)

        _point_latest(self.run_dir)
        return files


def _silence(stream: TextIO) -> None:
    """Point a closed pipe at devnull, so the interpreter doesn't fail flushing it again on exit."""
    with contextlib.suppress(OSError, ValueError, AttributeError):
        os.dup2(os.open(os.devnull, os.O_WRONLY), stream.fileno())


def _row(r: CheckResult) -> dict:
    d = asdict(r)
    d.pop("key")
    d["url"] = f"{r.ptype}://{r.proxy}"
    return d


def _csv_row(r: CheckResult) -> dict:
    """Like _row, but flat: target sites as "google.com:ok;discord.com:no"."""
    d = _row(r)
    d["targets"] = ";".join(f"{target_label(u, r.targets)}:{'ok' if ok else 'no'}" for u, ok in r.targets.items())
    return d


LATEST_POINTER = "latest.txt"


def _point_latest(run_dir: Path) -> None:
    """results/latest.txt always names the newest run; results/latest is also a symlink.

    The symlink is handy for looking around, but on Windows it needs admin or developer
    rights – the pointer file works everywhere.
    """
    atomic_write(run_dir.parent / LATEST_POINTER, run_dir.name + "\n")
    latest = run_dir.parent / "latest"
    try:
        if latest.is_symlink():
            latest.unlink()
        if not latest.exists():
            os.symlink(run_dir.name, latest, target_is_directory=True)
    except OSError:
        pass  # no symlinks allowed – latest.txt is enough


def latest_run_dir(results_dir: Path = RESULTS_DIR) -> Optional[Path]:
    pointer = results_dir / LATEST_POINTER
    try:
        name = pointer.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):  # missing, no permission or broken -> try the symlink
        name = ""
    # only a folder name directly under results/ – empty, "..", or paths like "a/../.." would
    # otherwise point to results/ itself or outside of it
    if name and name not in (".", "..") and Path(name).name == name:
        run_dir = results_dir / name
        if run_dir.is_dir():
            return run_dir
    link = results_dir / "latest"
    return link if link.is_dir() else None  # runs from older versions without latest.txt


def has_latest_results(results_dir: Path = RESULTS_DIR) -> bool:
    """Is there a last run with hits? Doesn't read the whole file for that."""
    run_dir = latest_run_dir(results_dir)
    try:
        return run_dir is not None and (run_dir / "all.txt").stat().st_size > 0
    except OSError:
        return False


def latest_results(results_dir: Path = RESULTS_DIR) -> List[str]:
    """Proxies of the last run for --recheck without a file."""
    run_dir = latest_run_dir(results_dir)
    path = run_dir / "all.txt" if run_dir else None
    return path.read_text(encoding="utf-8").splitlines() if path and path.exists() else []
