"""Workflows install Python packages only from hash-locked files (#292, OpenSSF Scorecard Pinned-Dependencies)."""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.y*ml"))
LOCKS = sorted((ROOT / ".github" / "requirements").glob("*.txt"))
# pip, pip3, python -m pip, with any spacing
INSTALL = re.compile(r"\bpip3?\s+install\b([^\n]*)")
LOCKED = r" (--quiet )?-r \.github/requirements/\w+\.txt"
# our own freshly built wheel is the one exception – it's what those steps test. Only these exact forms.
OWN_WHEEL = {" dist/*.whl", ' "$(ls $GITHUB_WORKSPACE/dist/*.whl)[mcp]"'}


def installs(text):
    return INSTALL.findall(text)


@pytest.mark.parametrize("text,ok", [
    ("pip install -r .github/requirements/test.txt", True),
    ("pip install dist/*.whl", True),
    ("pip install requests", False),
    ("pip3 install requests", False),
    ("python -m pip  install requests", False),
    ("pip install dist/*.whl requests", False),
])
def test_the_check_catches_every_spelling(text, ok):
    assert all(args in OWN_WHEEL or re.fullmatch(LOCKED, args) for args in installs(text)) is ok


@pytest.mark.parametrize("workflow", WORKFLOWS, ids=lambda p: p.name)
def test_every_pip_install_uses_a_lock_file(workflow):
    for args in installs(workflow.read_text(encoding="utf-8")):
        if args in OWN_WHEEL:
            continue
        assert re.fullmatch(LOCKED, args), f"{workflow.name}: pip install{args}"


def requirements(path):
    """(name, specifier) from a .in or requirements file, following -r includes."""
    from packaging.requirements import Requirement

    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#")[0].strip()
        if line.startswith("-r "):
            out += requirements(path.parent / line[3:].strip())
        elif line:
            out.append(Requirement(line))
    return out


@pytest.mark.parametrize("source", sorted((ROOT / ".github" / "requirements").glob("*.in")), ids=lambda p: p.name)
def test_each_lock_satisfies_its_source(source):
    """A bumped requirement (say discord.py>=2.8) must not keep installing an older locked version."""
    from packaging.utils import canonicalize_name

    lock = source.with_suffix(".txt").read_text(encoding="utf-8")
    locked = {}
    for name, version in re.findall(r"^([A-Za-z0-9_.-]+)==(\S+)", lock, re.MULTILINE):
        locked.setdefault(canonicalize_name(name), []).append(version)
    for req in requirements(source):
        versions = locked.get(canonicalize_name(req.name))
        assert versions, f"{source.name}: {req.name} is not in the lock – run compile.sh"
        assert any(req.specifier.contains(v, prereleases=True) for v in versions), \
            f"{source.name}: locked {req.name} {versions} doesn't satisfy {req.specifier} – run compile.sh"


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
