"""The real command line against the localhost lab (tests/lab.py): a deterministic smoke test for merge checks.

    python .github/scripts/lab_smoke.py

Starts the lab's check targets and a few proxies with known behaviour on 127.0.0.1, then runs proxy-scraper
(--pick --verify, --diagnose) in child processes and checks stdout, stderr and the exit codes. Nothing leaves
the machine: the hourly list comes from a fixture, the check targets are the lab's. Three seams are swapped,
the same ones the tests and docs/demo use: verify.prepare (the lab's checker), api._live_fetch (the fixture
list) and agent.listable (the lab lives on 127.0.0.1, which a real list may not name).

The proxyscraper package is the one Python finds first – an installed wheel or the container's – the checkout
only supplies tests/lab.py. With PROXY_SCRAPER_SMOKE_INSTALLED=1 the script fails if proxyscraper was imported
from the checkout instead of an installation.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(ROOT))  # last: an installed proxyscraper wins over the checkout's


def _child(state_file: str, argv: list) -> int:
    """One proxy-scraper command, pointed at the running lab."""
    from proxyscraper import agent, api, cli, verify
    from tests.lab import Lab

    state = json.loads(Path(state_file).read_text(encoding="utf-8"))
    lab = Lab()
    lab.judge_port, lab.confirm_port, lab.tls_port = state["judge_port"], state["confirm_port"], state["tls_port"]

    async def prepare(timeout, connect_timeout):
        return await lab.checker(timeout=min(timeout, 2.0))

    async def live_fetch(url, timeout=0, headers=None):
        return json.dumps(state["rows" if url.endswith("proxies.json") else "stats"]).encode()

    verify.prepare = prepare
    api._live_fetch = live_fetch
    agent.listable = lambda proxy: True
    return cli.run(argv)


def _row(proxy: str, latency: int) -> dict:
    return {"url": f"http://{proxy}", "proxy": proxy, "ptype": "http", "latency": latency, "exit_ip": "",
            "https": True, "anonymity": "elite", "country": "DE", "streak": 30, "uptime_7d": 95}


def _run(state_file: str, *argv: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "NO_COLOR": "1"}
    proc = subprocess.run([sys.executable, __file__, "--child", state_file, *argv], capture_output=True, text=True,
                          encoding="utf-8", env=env, timeout=120)
    print(f"$ proxy-scraper {' '.join(argv)}  -> exit {proc.returncode}")
    return proc


def _expect(ok: bool, what: str, proc: subprocess.CompletedProcess) -> None:
    if not ok:
        sys.exit(f"FAILED: {what}\n--- stdout\n{proc.stdout}\n--- stderr\n{proc.stderr}")
    print(f"  ok: {what}")


def main() -> int:
    import proxyscraper
    from tests.lab import INJECTED, LabThread

    where = Path(proxyscraper.__file__).resolve()
    print(f"proxyscraper {proxyscraper.__version__} from {where.parent}")
    if os.environ.get("PROXY_SCRAPER_SMOKE_INSTALLED") == "1" and ROOT in where.parents:
        sys.exit(f"FAILED: proxyscraper was imported from the checkout ({where}), not from the installation")

    with LabThread() as lab, tempfile.TemporaryDirectory() as tmp:
        dead = lab.run(lab.closed_port())
        rewriting = lab.run(lab.proxy("203.0.113.13", rewrite=lambda body: INJECTED))
        no_https = lab.run(lab.proxy("203.0.113.15", no_connect=True))
        good = lab.run(lab.proxy("203.0.113.14"))
        updated = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat(timespec="seconds")
        state_file = str(Path(tmp) / "lab.json")
        Path(state_file).write_text(json.dumps({
            "judge_port": lab.judge_port, "confirm_port": lab.confirm_port, "tls_port": lab.tls_port,
            # best first: the good one comes last, so --verify has to reject the others to find it
            "rows": [_row(dead, 50), _row(rewriting, 60), _row(no_https, 70), _row(good, 80)],
            "stats": {"updated": updated, "run_hours": 1},
        }), encoding="utf-8")

        proc = _run(state_file, "--pick", "--verify", "--https-only")
        _expect(proc.returncode == 0 and proc.stdout == f"http://{good}\n",
                "--pick --verify --https-only prints only the proxy that passes every check", proc)

        proc = _run(state_file, "--pick", "4")
        _expect(proc.returncode == 0 and len(proc.stdout.split()) == 4, "--pick 4 prints the fixture list", proc)

        proc = _run(state_file, "--diagnose", good, "--json")
        report = json.loads(proc.stdout or "{}")
        _expect(proc.returncode == 0 and report.get("verdict") == "passed every check",
                "--diagnose: an honest proxy passes every check", proc)

        proc = _run(state_file, "--diagnose", rewriting, "--json")
        report = json.loads(proc.stdout or "{}")
        content = (report.get("checks") or {}).get("content") or {}
        _expect(proc.returncode == 1 and content.get("state") == "failed",
                "--diagnose: a proxy that changes the page fails the content check", proc)

        proc = _run(state_file, "--diagnose", no_https, "--json")
        report = json.loads(proc.stdout or "{}")
        https = (report.get("checks") or {}).get("https") or {}
        _expect(proc.returncode == 1 and https.get("state") == "failed",
                "--diagnose: a proxy that refuses CONNECT fails the HTTPS test", proc)

        proc = _run(state_file, "--diagnose", dead)
        _expect(proc.returncode == 1, "--diagnose: nothing listening is not usable", proc)
    print("lab smoke passed")
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--child":
        sys.exit(_child(sys.argv[2], sys.argv[3:]))
    sys.exit(main())
