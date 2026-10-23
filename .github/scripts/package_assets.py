"""Checks that an installed proxyscraper carries every package asset the code reads, and that they load.

    python -I .github/scripts/package_assets.py CHECKOUT

Run it with the Python of a fresh venv the wheel was installed into, from outside the checkout (-I keeps the
checkout and PYTHONPATH off sys.path). CHECKOUT is only read for pyproject.toml's package-data patterns and the
files they match there: each of those must be in the installed package, byte for byte the same size.
"""

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path
from typing import List


def patterns(checkout: Path) -> List[str]:
    """The proxyscraper entry of [tool.setuptools.package-data] in pyproject.toml (no tomllib: Python 3.9)."""
    text = (checkout / "pyproject.toml").read_text(encoding="utf-8")
    section = text.split("[tool.setuptools.package-data]", 1)[1].split("\n[", 1)[0]
    found = re.search(r"^proxyscraper\s*=\s*(\[.*?\])", section, re.M | re.S)
    if not found:
        raise SystemExit("pyproject.toml: no package-data for proxyscraper")
    return ast.literal_eval(found.group(1))


def expected_assets(checkout: Path) -> List[str]:
    """Every file in the checkout's package that a package-data pattern matches, relative to the package."""
    package = checkout / "proxyscraper"
    files = {p.relative_to(package).as_posix() for pattern in patterns(checkout) for p in package.glob(pattern)
             if p.is_file()}
    return sorted(files)


def main(checkout: Path) -> int:
    import proxyscraper

    installed = Path(proxyscraper.__file__).resolve().parent
    print(f"proxyscraper {proxyscraper.__version__} from {installed}")
    if checkout.resolve() in installed.parents or installed.parent == checkout.resolve():
        raise SystemExit("imported from the checkout, not from the installation – run it with python -I")

    expected = expected_assets(checkout)
    if not expected:
        raise SystemExit("the package-data patterns match nothing in the checkout")
    missing, different = [], []
    for name in expected:
        target = installed / name
        if not target.is_file():
            missing.append(name)
        elif target.stat().st_size != (checkout / "proxyscraper" / name).stat().st_size:
            different.append(name)
    if missing or different:
        raise SystemExit(f"missing from the installed package: {missing}; different size: {different}")
    print(f"{len(expected)} package assets installed: {', '.join(expected)}")

    # and they load the way the code reads them
    from proxyscraper import publish, sources
    from proxyscraper.server import status

    curated, meta = sources.load_source_file()
    assert curated, "sources.json has no sources"
    json.loads(sources.SOURCES_FILE.read_text(encoding="utf-8"))
    assert status.DASHBOARD_HTML.lstrip().lower().startswith(b"<!doctype html"), "dashboard.html"
    index = (publish.SITE / "index.html").read_text(encoding="utf-8")
    assert "<html" in index.lower(), "site/index.html"
    print(f"sources.json: {len(curated)} curated + {len(meta)} meta sources; dashboard.html and site/index.html load")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    sys.exit(main(Path(sys.argv[1])))
