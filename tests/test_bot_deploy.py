"""The bot's deployment (bot/deploy/install.sh, .github/workflows/bot.yml).

- the server installs the versions the bot's CI tested, hash-checked: one runtime lock (bot/requirements.lock),
  and the CI lock (.github/requirements/bot.txt) pins the same runtime versions plus the test tools
- every release gets a fresh directory and venv; /opt/proxybot/current switches only after the new venv imports
  the bot, the release before stays as /opt/proxybot/previous, and a bot that doesn't come up is rolled back

The release logic runs here for real against a fake prefix, with python3, systemctl and friends as stubs.
"""

import os
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
INSTALL = ROOT / "bot" / "deploy" / "install.sh"
RUNTIME_LOCK = ROOT / "bot" / "requirements.lock"
TEST_LOCK = ROOT / ".github" / "requirements" / "bot.txt"


def pins(path):
    """{(name, marker): version} of a uv lock file."""
    out = {}
    for name, version, marker in re.findall(r"^([A-Za-z0-9_.-]+)==([^\s;]+)\s*(?:;\s*([^\\\n]*?))?\s*\\?$",
                                            path.read_text(encoding="utf-8"), re.M):
        out[(name.lower(), marker.strip())] = version
    return out


# --------------------------------------------------------------------------- one tested, hash-locked runtime

def test_install_uses_the_hashed_runtime_lock():
    script = INSTALL.read_text(encoding="utf-8")
    installs = re.findall(r"pip\"? install[^\n]*", script)
    assert installs, "install.sh installs nothing"
    for line in installs:
        assert "--require-hashes" in line and "requirements.lock" in line, line
    assert "requirements.txt" not in "\n".join(installs)


def test_the_runtime_lock_has_hashes_and_satisfies_requirements_txt():
    from packaging.requirements import Requirement
    from packaging.utils import canonicalize_name

    text = RUNTIME_LOCK.read_text(encoding="utf-8")
    blocks = re.split(r"\n(?=[A-Za-z0-9_.-]+==)", text)
    assert all("--hash=sha256:" in b for b in blocks if re.match(r"[A-Za-z0-9_.-]+==", b))
    assert "pytest" not in text  # test tools are not deployed
    locked = pins(RUNTIME_LOCK)
    for line in (ROOT / "bot" / "requirements.txt").read_text(encoding="utf-8").splitlines():
        line = line.split("#")[0].strip()
        if line:
            req = Requirement(line)
            versions = [v for (name, _), v in locked.items() if canonicalize_name(name) == canonicalize_name(req.name)]
            assert versions and all(req.specifier.contains(v) for v in versions), req


def test_ci_tests_exactly_the_deployed_runtime_versions():
    runtime, tested = pins(RUNTIME_LOCK), pins(TEST_LOCK)
    assert runtime
    for key, version in runtime.items():
        assert tested.get(key) == version, f"{key}: deployed {version}, tested {tested.get(key)}"
    assert any(name == "pytest" for name, _ in tested)
    source = (ROOT / ".github" / "requirements" / "bot.in").read_text(encoding="utf-8")
    assert "-c ../../bot/requirements.lock" in source  # the test lock can't drift from the runtime lock


def test_the_workflow_tests_with_the_test_lock_and_deploys_into_a_fresh_release():
    data = yaml.safe_load((ROOT / ".github" / "workflows" / "bot.yml").read_text(encoding="utf-8"))
    test = "\n".join(str(s.get("run", "")) for s in data["jobs"]["test"]["steps"])
    assert "--require-hashes -r .github/requirements/bot.txt" in test
    deploy = "\n".join(str(s.get("run", "")) for s in data["jobs"]["deploy"]["steps"])
    assert "RELEASE=/opt/proxybot/releases/$release" in deploy
    assert "mkdir /opt/proxybot/releases/$release;" in deploy  # fresh: fails if it already exists
    assert 'install.sh $RELEASE"' in deploy
    assert "/opt/proxybot/app" not in deploy  # no more copying over the running code


def test_the_service_runs_the_current_release():
    unit = (ROOT / "bot" / "deploy" / "proxybot.service").read_text(encoding="utf-8")
    assert "WorkingDirectory=/opt/proxybot/current\n" in unit
    assert "ExecStart=/opt/proxybot/current/venv/bin/python -m proxybot\n" in unit


# --------------------------------------------------------------------------- the release logic, for real

STUBS = {
    # -m venv DIR: a venv whose pip logs what it installs and whose python fails the import check in a release
    # that has a file BROKEN
    "python3": """#!/bin/sh
if [ "$1" = -m ] && [ "$2" = venv ]; then
  mkdir -p "$3/bin"
  printf '#!/bin/sh\\necho "pip $*" >> "$FAKE_LOG"\\n' > "$3/bin/pip"
  printf '#!/bin/sh\\n[ ! -e BROKEN ]\\n' > "$3/bin/python"
  chmod +x "$3/bin/pip" "$3/bin/python"
  echo "venv $3" >> "$FAKE_LOG"
fi
exit 0
""",
    # is-active fails while current points at a release with a file CRASHES
    "systemctl": """#!/bin/sh
echo "systemctl $*" >> "$FAKE_LOG"
if [ "$1" = is-active ]; then
  [ ! -e "$PROXYBOT_BASE/current/CRASHES" ]
fi
""",
    "journalctl": "#!/bin/sh\necho 'bot log line'\n",
    "id": "#!/bin/sh\nexit 0\n",
    "useradd": "#!/bin/sh\nexit 0\n",
    "chown": "#!/bin/sh\nexit 0\n",
    "apt-get": "#!/bin/sh\nexit 0\n",
}


@pytest.fixture
def server(tmp_path):
    if sys.platform == "win32" or not shutil.which("sh"):
        pytest.skip("needs a POSIX sh")
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    for name, body in STUBS.items():
        (stubs / name).write_text(body)
        (stubs / name).chmod(stat.S_IRWXU)
    base = tmp_path / "opt" / "proxybot"
    (base / "releases").mkdir(parents=True)
    (tmp_path / "units").mkdir()
    env_file = tmp_path / "proxybot.env"
    env_file.write_text("DISCORD_TOKEN=x\n")
    log = tmp_path / "log"
    log.write_text("")
    env = {**os.environ, "PATH": f"{stubs}{os.pathsep}{os.environ['PATH']}", "PROXYBOT_BASE": str(base),
           "PROXYBOT_UNIT_DIR": str(tmp_path / "units"), "PROXYBOT_ENV_FILE": str(env_file),
           "PROXYBOT_SETTLE": "0", "PROXYBOT_KEEP": "3", "FAKE_LOG": str(log)}

    class Server:
        def release(self, name, broken=False, crashes=False):
            """What the workflow unpacks: the bot directory without tests."""
            rel = base / "releases" / name
            shutil.copytree(ROOT / "bot", rel, ignore=shutil.ignore_patterns("tests", "__pycache__", ".venv"))
            if broken:
                (rel / "BROKEN").write_text("")
            if crashes:
                (rel / "CRASHES").write_text("")
            return rel

        def install(self, *args):
            log.write_text("")
            return subprocess.run(["sh", str(INSTALL), *map(str, args)], env=env, capture_output=True, text=True,
                                  timeout=60)

        def current(self):
            link = base / "current"
            return Path(os.readlink(link)).name if link.is_symlink() else None

        def previous(self):
            link = base / "previous"
            return Path(os.readlink(link)).name if link.is_symlink() else None

        def log(self):
            return log.read_text()

        releases = base / "releases"
        unit = tmp_path / "units" / "proxybot.service"

    return Server()


def test_a_release_gets_its_own_venv_from_the_lock_and_becomes_current(server):
    rel = server.release("r1")
    proc = server.install(rel)
    assert proc.returncode == 0, proc.stderr
    assert server.current() == "r1" and server.previous() is None
    log = server.log()
    assert f"venv {rel}/venv" in log
    assert f"pip install -q --disable-pip-version-check --require-hashes -r {rel}/requirements.lock" in log
    assert "systemctl restart proxybot" in log
    assert server.unit.read_text() == (rel / "deploy" / "proxybot.service").read_text()


def test_the_next_release_keeps_the_one_before_as_previous(server):
    assert server.install(server.release("r1")).returncode == 0
    assert server.install(server.release("r2")).returncode == 0
    assert (server.current(), server.previous()) == ("r2", "r1")


def test_a_release_that_does_not_import_is_never_switched_to(server):
    assert server.install(server.release("r1")).returncode == 0
    proc = server.install(server.release("r2", broken=True))
    assert proc.returncode != 0
    assert server.current() == "r1"  # the running bot was not touched
    assert "restart" not in server.log()


def test_a_bot_that_does_not_come_up_is_rolled_back(server):
    assert server.install(server.release("r1")).returncode == 0
    proc = server.install(server.release("r2", crashes=True))
    assert proc.returncode != 0
    assert "bot log line" in proc.stderr and "rolling back to r1" in proc.stderr
    assert server.current() == "r1"
    assert server.log().count("systemctl restart proxybot") == 2  # the new one, then the old one again
    assert server.unit.read_text() == (server.releases / "r1" / "deploy" / "proxybot.service").read_text()


def test_rollback_by_hand_goes_back_to_the_previous_release(server):
    assert server.install(server.release("r1")).returncode == 0
    assert server.install(server.release("r2")).returncode == 0
    proc = server.install("--rollback")
    assert proc.returncode == 0, proc.stderr
    assert (server.current(), server.previous()) == ("r1", "r2")
    assert "systemctl restart proxybot" in server.log()


def test_rollback_without_a_previous_release_says_so(server):
    assert server.install(server.release("r1")).returncode == 0
    proc = server.install("--rollback")
    assert proc.returncode != 0 and "no previous release" in proc.stderr
    assert server.current() == "r1"


def test_old_releases_are_pruned_but_current_and_previous_stay(server):
    for name in ("r1", "r2", "r3", "r4", "r5"):
        assert server.install(server.release(name)).returncode == 0
    assert sorted(p.name for p in server.releases.iterdir()) == ["r3", "r4", "r5"]
    assert (server.current(), server.previous()) == ("r5", "r4")


def test_only_releases_under_the_prefix_are_installed(server, tmp_path):
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    proc = server.install(elsewhere)
    assert proc.returncode != 0 and "releases" in proc.stderr
