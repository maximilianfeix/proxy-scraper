"""What the merge checks run and what they leave to a scheduled smoke test.

- tests that a pull request has to pass never depend on public proxies or the live list being up (#review 10):
  they run against fixtures and the localhost lab; the real internet checks run on a schedule, not as a merge check
- the Parquet round-trip of the Hugging Face mirror really runs somewhere (PyArrow is not in the normal matrix)
- a wheel built from the sdist carries every package asset the code reads
"""

import ast
import importlib.util
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"


def workflow(name):
    return yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))


def triggers(data):
    # PyYAML reads the key `on` as True
    return data.get("on", data.get(True)) or {}


def run_lines(job):
    return "\n".join(str(step.get("run", "")) for step in job.get("steps") or [])


def runs_on_pull_requests(data):
    on = triggers(data)
    return "pull_request" in on or "pull_request_target" in on


# --------------------------------------------------------------------------- merge checks are deterministic

def test_the_action_job_reads_a_fixture_list_not_the_live_one():
    job = workflow("tests.yml")["jobs"]["action"]
    env = job.get("env") or {}
    assert env.get("PROXY_SCRAPER_LIVE_FIXTURE") == "1"
    assert env.get("PYTHONPATH", "").endswith(".github/scripts/live_fixture")
    assert (ROOT / ".github" / "scripts" / "live_fixture" / "sitecustomize.py").is_file()
    steps = job["steps"]
    action = next(s for s in steps if s.get("uses") == "./")
    assert action["with"].get("recheck", "false") == "false"  # a recheck would contact the proxies


def test_the_docker_merge_check_uses_the_lab_not_public_proxies():
    data = workflow("docker.yml")
    assert runs_on_pull_requests(data)
    script = run_lines(data["jobs"]["test"])
    assert "--want" not in script and "--limit" not in script  # no real scan in a merge check
    assert ".github/scripts/lab_smoke.py" in script


def test_no_merge_check_scans_or_picks_from_the_internet():
    for path in sorted(WORKFLOWS.glob("*.yml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not runs_on_pull_requests(data):
            continue
        for name, job in data["jobs"].items():
            script = run_lines(job)
            assert not re.search(r"proxy-scraper(:test)?\s.*--want", script), f"{path.name}:{name}"
            assert "--recheck live" not in script, f"{path.name}:{name}"


def test_the_live_checks_still_run_on_a_schedule_and_by_hand():
    data = workflow("live-smoke.yml")
    on = triggers(data)
    assert "schedule" in on and "workflow_dispatch" in on
    assert not runs_on_pull_requests(data) and "push" not in on  # visible, but never a merge check
    jobs = data["jobs"]
    assert any(step.get("uses") == "./" for job in jobs.values() for step in job.get("steps") or [])
    assert any("--want" in run_lines(job) for job in jobs.values())  # the real scan inside the container


def test_the_lab_smoke_passes():
    proc = subprocess.run([sys.executable, str(ROOT / ".github" / "scripts" / "lab_smoke.py")],
                          capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "lab smoke passed" in proc.stdout


def test_the_live_fixture_answers_like_the_hourly_list(monkeypatch):
    from proxyscraper import agent, api

    monkeypatch.setenv("PROXY_SCRAPER_LIVE_FIXTURE", "1")
    monkeypatch.setattr(api, "_live_fetch", api._live_fetch)
    monkeypatch.setattr(agent, "listable", agent.listable)
    spec = importlib.util.spec_from_file_location(
        "live_fixture_sitecustomize", ROOT / ".github" / "scripts" / "live_fixture" / "sitecustomize.py")
    spec.loader.exec_module(importlib.util.module_from_spec(spec))
    found = api.live_proxies(types=["socks5", "http"], https=True, limit=5)
    assert 1 <= len(found) <= 5
    assert all(p.ptype in ("socks5", "http") and p.https for p in found)


# --------------------------------------------------------------------------- PyArrow really runs somewhere

def test_a_linux_job_runs_the_parquet_round_trip_with_pyarrow_required():
    job = workflow("tests.yml")["jobs"]["parquet"]
    assert job["runs-on"] == "ubuntu-latest"
    assert (job.get("env") or {}).get("PROXY_SCRAPER_REQUIRE_PYARROW") == "1"
    script = run_lines(job)
    assert "--require-hashes -r .github/requirements/test.txt" in script
    assert "--require-hashes -r .github/requirements/hf.txt" in script
    assert "tests/test_hf_parquet.py" in script


# --------------------------------------------------------------------------- sdist -> wheel -> installed assets

def package_data():
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    section = text.split("[tool.setuptools.package-data]", 1)[1].split("\n[", 1)[0]
    return ast.literal_eval(re.search(r"^proxyscraper\s*=\s*(\[.*?\])", section, re.M | re.S).group(1))


def test_the_asset_check_knows_every_package_data_pattern():
    spec = importlib.util.spec_from_file_location("package_assets", ROOT / ".github" / "scripts" / "package_assets.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.patterns(ROOT) == package_data()
    expected = module.expected_assets(ROOT)
    assert "sources.json" in expected and "server/dashboard.html" in expected and "site/index.html" in expected


def test_a_job_builds_the_wheel_from_the_sdist_and_checks_the_installed_assets():
    job = workflow("tests.yml")["jobs"]["sdist"]
    script = run_lines(job)
    assert "python -m build --sdist" in script
    assert re.search(r"python -m build --wheel [^\n]*from-sdist", script)
    assert ".github/scripts/package_assets.py" in script
    assert re.search(r'python"? -I ', script)  # the installed package, never the checkout


@pytest.mark.parametrize("name", ["package"])
def test_the_existing_wheel_and_mcp_smokes_stay(name):
    script = run_lines(workflow("tests.yml")["jobs"][name])
    assert "pip install dist/*.whl" in script and "proxy-scraper-mcp" in script
