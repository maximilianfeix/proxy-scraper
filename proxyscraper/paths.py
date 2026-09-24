"""Ablageorte: Konfiguration im Projektordner, gelernter Zustand in data/, Ergebnisse in results/."""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_DIR / "data"
RESULTS_DIR = PROJECT_DIR / "results"


def atomic_write(path: Path, text: str) -> None:
    # Erst temporär schreiben, dann umbenennen – ein Abbruch hinterlässt keine halbe Datei
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)
