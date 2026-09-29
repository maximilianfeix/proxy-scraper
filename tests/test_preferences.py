import json

import pytest

from proxyscraper import preferences


@pytest.fixture(autouse=True)
def prefs_file(tmp_path, monkeypatch):
    path = tmp_path / "preferences.json"
    monkeypatch.setattr(preferences, "PREFERENCES_FILE", path)
    return path


def test_star_hint_once_on_the_second_run_with_hits():
    assert [preferences.star_hint_due(env={}) for _ in range(4)] == [False, True, False, False]


@pytest.mark.parametrize("env", [{"CI": "true"}, {"PROXY_SCRAPER_NO_STAR_HINT": "1"}])
def test_star_hint_never_in_ci_or_when_turned_off(env, prefs_file):
    assert not any(preferences.star_hint_due(env=env) for _ in range(3))
    assert not prefs_file.exists()


def test_star_hint_and_last_argv_share_the_file(prefs_file):
    preferences.save_last_argv(["--want", "20"])
    preferences.star_hint_due(env={})
    preferences.save_last_argv(["--want", "30"])
    assert preferences.load_last_argv() == ["--want", "30"]
    assert json.loads(prefs_file.read_text())["runs_with_hits"] == 1


def test_broken_file_starts_over(prefs_file):
    prefs_file.write_text("[1, 2")
    assert preferences.load_last_argv() is None
    assert preferences.star_hint_due(env={}) is False
    assert preferences.star_hint_due(env={}) is True
