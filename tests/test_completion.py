import shutil
import subprocess
import sys

import pytest

from proxyscraper import cli, completion


def generate(shell, capsys):
    with pytest.raises(SystemExit) as exit_info:
        cli.parse_args(["--completion", shell])
    assert exit_info.value.code == 0
    return capsys.readouterr().out


@pytest.mark.parametrize("shell", completion.SHELLS)
def test_every_option_is_in_the_script(shell, capsys):
    out = generate(shell, capsys)
    for flag in ("--types", "--rotate", "--no-datacenter", "--serve-host", "--recheck"):
        assert flag.lstrip("-") in out
    assert "round-robin" in out and "socks5" in out  # Auswahlwerte kommen mit


def test_short_help_keeps_abbreviations():
    assert completion.short_help("max. Zeit für den Aufbau (Standard: 3)") == "max. Zeit für den Aufbau"
    assert completion.short_help("nur diese Länder, z. B. DE,AT,CH") == "nur diese Länder"
    assert completion.short_help("x" * 80).endswith("…")


def test_zsh_braces_stay_outside_the_quotes(capsys):
    out = generate("zsh", capsys)
    assert "'(-c --concurrency)'{-c,--concurrency}'[" in out
    assert "{_files; compadd live}" in out
    assert "--types[welche Protokolle]:*-*:types:(http socks4 socks5)" in out


def test_help_text_is_german(capsys):
    out = generate("fish", capsys)
    assert "Hilfe anzeigen" in out and "show this help" not in out


# unter Windows ist "bash" meist WSL und sieht die Windows-Pfade nicht – dort braucht es das auch nicht
needs_bash = pytest.mark.skipif(not shutil.which("bash") or sys.platform == "win32", reason="kein bash")


def complete_bash(script, cwd, *words):
    """_proxy_scraper mit COMP_WORDS aufrufen, eine Zeile pro Vorschlag."""
    quoted = " ".join("'" + w + "'" for w in words)
    code = (script + f'\nCOMP_WORDS=({quoted}); COMP_CWORD={len(words) - 1}; _proxy_scraper; '
            'printf "%s\\n" "${COMPREPLY[@]}"\n')
    out = subprocess.run(["bash", "-s"], input=code, capture_output=True, text=True, check=True, cwd=cwd).stdout
    return [line for line in out.splitlines() if line]


@needs_bash
def test_bash_completes_values(capsys, tmp_path):
    script = generate("bash", capsys)
    assert complete_bash(script, tmp_path, "proxy-scraper", "--rotate", "r") == ["random", "round-robin"]
    assert complete_bash(script, tmp_path, "proxy-scraper", "--no-d") == ["--no-datacenter", "--no-discover"]


@needs_bash
def test_bash_offers_more_types_after_the_first(capsys, tmp_path):
    script = generate("bash", capsys)
    assert complete_bash(script, tmp_path, "proxy-scraper", "--types", "http", "s") == ["socks4", "socks5"]
    assert complete_bash(script, tmp_path, "proxy-scraper", "--types", "http", "--fa") == ["--fast"]


@needs_bash
def test_bash_keeps_paths_with_spaces_together(capsys, tmp_path):
    (tmp_path / "meine liste.txt").write_text("")
    script = generate("bash", capsys)
    assert complete_bash(script, tmp_path, "proxy-scraper", "--recheck", "m") == ["meine liste.txt"]
    assert complete_bash(script, tmp_path, "proxy-scraper", "--recheck", "l") == ["live"]


@pytest.mark.skipif(not shutil.which("zsh"), reason="kein zsh")
def test_zsh_script_parses(capsys, tmp_path):
    script = tmp_path / "comp.zsh"
    script.write_text(generate("zsh", capsys))
    subprocess.run(["zsh", "-n", str(script)], check=True)
