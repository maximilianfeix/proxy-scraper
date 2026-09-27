"""The GitHub Action: inputs from the environment, proxies from the hourly list, outputs for the next steps."""

from pathlib import Path

from proxyscraper import action
from proxyscraper.checker import CheckResult


def fake(n, **extra):
    return [CheckResult(f"socks5 1.1.1.{i}:1080", "socks5", f"1.1.1.{i}:1080", 100 + i, "1.1.1.1", True, "elite", "DE")
            for i in range(n)]


def run(monkeypatch, tmp_path, env, found=3, rechecked=None):
    calls = {}

    def live(**kwargs):
        calls["live"] = kwargs
        return fake(found)

    def check(urls, **kwargs):
        calls["check"] = list(urls)
        return fake(found)[:rechecked]
    monkeypatch.setattr(action, "live_proxies", live)
    monkeypatch.setattr(action, "check_proxies", check)
    out = tmp_path / "out.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    code = action.main()
    outputs = dict(line.split("=", 1) for line in out.read_text().splitlines()) if out.exists() else {}
    return code, outputs, calls


def test_filters_reach_live_proxies_and_outputs_are_set(monkeypatch, tmp_path):
    code, out, calls = run(monkeypatch, tmp_path, {
        "PS_TYPES": "socks5, http", "PS_COUNTRIES": "de,nl", "PS_HTTPS": "true", "PS_MIN_UPTIME": "90",
        "PS_WORKS_ON": "google", "PS_LIMIT": "2"})
    assert code == 0
    assert calls["live"] == {"types": ["socks5", "http"], "countries": "de,nl", "https": True, "min_uptime": 90,
                             "works_on": ["google"], "limit": 2}
    assert out["proxy"] == "socks5://1.1.1.0:1080" and out["count"] == "2"  # limit
    file = out["file"]
    assert file.startswith(str(tmp_path)) and Path(file).read_text().splitlines()[0] == "socks5://1.1.1.0:1080"


def test_two_uses_in_one_job_get_their_own_files(monkeypatch, tmp_path):
    _, first, _ = run(monkeypatch, tmp_path, {"PS_LIMIT": "1"})
    _, second, _ = run(monkeypatch, tmp_path, {"PS_LIMIT": "2"})
    assert first["file"] != second["file"] and len(Path(first["file"]).read_text().splitlines()) == 1


def test_recheck_keeps_only_what_works_from_the_runner(monkeypatch, tmp_path):
    _, out, calls = run(monkeypatch, tmp_path, {"PS_RECHECK": "true", "PS_LIMIT": "2"}, found=5, rechecked=1)
    assert calls["live"]["limit"] == 0  # recheck starts from all of them, the limit applies afterwards
    assert len(calls["check"]) == 5 and out["count"] == "1"


def test_nothing_found_fails_the_step_unless_allowed(monkeypatch, tmp_path, capsys):
    code, out, _ = run(monkeypatch, tmp_path, {}, found=0)
    assert code == 1 and "::error::" in capsys.readouterr().out
    code, out, _ = run(monkeypatch, tmp_path, {"PS_FAIL_IF_EMPTY": "false"}, found=0)
    assert code == 0 and out["count"] == "0" and out["proxy"] == ""


def test_bad_inputs_are_explained(monkeypatch, tmp_path, capsys):
    code, _, _ = run(monkeypatch, tmp_path, {"PS_LIMIT": "lots"})
    assert code == 1 and "limit" in capsys.readouterr().out
