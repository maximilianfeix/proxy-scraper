"""Workflows install Python packages only from hash-locked files (#292, OpenSSF Scorecard Pinned-Dependencies)."""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.y*ml"))
LOCKS = sorted((ROOT / ".github" / "requirements").glob("*.txt"))
INSTALL = re.compile(r"pip install\b([^\n]*)")


@pytest.mark.parametrize("workflow", WORKFLOWS, ids=lambda p: p.name)
def test_every_pip_install_uses_a_lock_file(workflow):
    for args in INSTALL.findall(workflow.read_text(encoding="utf-8")):
        # our own freshly built wheel is the one exception: it's what the step tests
        if "dist/*.whl" in args:
            continue
        assert re.search(r"-r \.github/requirements/\w+\.txt", args), f"{workflow.name}: pip install{args}"


def test_the_lock_files_exist_and_every_package_has_hashes():
    assert {p.stem for p in LOCKS} >= {"test", "lint", "run", "hf", "bot"}
    for lock in LOCKS:
        text = lock.read_text(encoding="utf-8")
        packages = re.findall(r"^[A-Za-z0-9_.-]+==\S+", text, re.MULTILINE)
        assert packages, lock.name
        # each requirement block carries at least one --hash
        blocks = re.split(r"\n(?=[A-Za-z0-9_.-]+==)", text)
        assert all("--hash=sha256:" in block for block in blocks if re.match(r"[A-Za-z0-9_.-]+==", block)), lock.name


def test_lint_uses_the_ruff_version_pyproject_pins():
    pin = re.search(r'"ruff==([\d.]+)"', (ROOT / "pyproject.toml").read_text()).group(1)
    assert f"ruff=={pin} " in (ROOT / ".github" / "requirements" / "lint.txt").read_text()
