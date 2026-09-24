from pathlib import Path

import pytest

from proxyscraper import __version__, paths
from proxyscraper.cli import parse_args


@pytest.mark.parametrize("platform, env, expected", [
    ("darwin", {}, "/home/x/Library/Application Support/proxy-scraper"),
    ("win32", {"LOCALAPPDATA": "/appdata"}, "/appdata/proxy-scraper"),
    ("linux", {}, "/home/x/.local/share/proxy-scraper"),
    ("linux", {"XDG_DATA_HOME": "/xdg"}, "/xdg/proxy-scraper"),
])
def test_user_data_dir(platform, env, expected):
    assert paths.user_data_dir(platform, env, Path("/home/x")) == Path(expected)


def test_env_overrides_data_dir(tmp_path):
    assert paths.data_dir({"PROXY_SCRAPER_HOME": str(tmp_path)}) == tmp_path


def test_checkout_detection(tmp_path):
    assert paths.is_checkout()  # die Tests laufen aus dem Repo
    assert not paths.is_checkout(tmp_path)


def test_sources_ship_inside_the_package():
    from proxyscraper import sources

    assert sources.SOURCES_FILE.parent == paths.PACKAGE_DIR and sources.SOURCES_FILE.is_file()


def test_version_flag(capsys):
    with pytest.raises(SystemExit) as exit_info:
        parse_args(["--version"])
    assert exit_info.value.code == 0
    assert capsys.readouterr().out.strip() == f"proxy-scraper {__version__}"
