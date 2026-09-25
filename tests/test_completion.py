import shutil
import subprocess

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


def test_help_text_is_german(capsys):
    out = generate("fish", capsys)
    assert "Hilfe anzeigen" in out and "show this help" not in out


@pytest.mark.skipif(not shutil.which("bash"), reason="kein bash")
def test_bash_completes_values(capsys, tmp_path):
    script = tmp_path / "comp.bash"
    script.write_text(generate("bash", capsys))
    run = ('source "$1"; COMP_WORDS=(proxy-scraper --rotate r); COMP_CWORD=2; _proxy_scraper; '
           'echo "${COMPREPLY[*]}"; COMP_WORDS=(proxy-scraper --no-d); COMP_CWORD=1; _proxy_scraper; '
           'echo "${COMPREPLY[*]}"')
    out = subprocess.run(["bash", "-c", run, "_", str(script)], capture_output=True, text=True, check=True).stdout
    assert out.splitlines() == ["random round-robin", "--no-datacenter --no-discover"]


@pytest.mark.skipif(not shutil.which("zsh"), reason="kein zsh")
def test_zsh_script_parses(capsys, tmp_path):
    script = tmp_path / "comp.zsh"
    script.write_text(generate("zsh", capsys))
    subprocess.run(["zsh", "-n", str(script)], check=True)
