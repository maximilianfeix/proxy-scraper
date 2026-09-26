"""PyPI and the MCP registry (#42): one package name everywhere, and server.json that the registry accepts."""

import json
import re
from pathlib import Path

import pytest

from proxyscraper import __version__, cli, mcp_entry

ROOT = Path(__file__).parent.parent
PACKAGE = "proxy-scraper-cli"


def pyproject():
    return (ROOT / "pyproject.toml").read_text(encoding="utf-8")


def test_the_package_is_called_proxy_scraper_cli_with_all_three_commands():
    text = pyproject()
    assert re.search(r'^name = "proxy-scraper-cli"$', text, re.M)
    for script in ('proxy-scraper = "proxyscraper.cli:run"', 'proxy-scraper-cli = "proxyscraper.cli:run"',
                   'proxy-scraper-mcp = "proxyscraper.mcp_entry:main"'):
        assert script in text


def test_mcp_flag_starts_the_mcp_server(monkeypatch):
    calls = []
    monkeypatch.setattr(mcp_entry, "main", lambda: calls.append("mcp") or 0)
    assert cli.run(["--mcp"]) == 0 and calls == ["mcp"]


def test_install_hints_use_the_package_name():
    assert f'pip install "{PACKAGE}[mcp]"' in mcp_entry.INSTALL_HINT
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert f"pipx install {PACKAGE}" in readme
    assert 'proxy-scraper[mcp] @ git+' not in readme  # the old git-only install line is gone


def test_server_json_matches_the_package_and_the_readme():
    server = json.loads((ROOT / "server.json").read_text(encoding="utf-8"))
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert f"<!-- mcp-name: {server['name']} -->" in readme  # how the registry checks we own the PyPI package
    (package,) = server["packages"]
    assert package["registryType"] == "pypi" and package["identifier"] == PACKAGE
    assert server["version"] == package["version"] == __version__  # the release workflow keeps them in sync too
    args = [a.get("name") for a in package["packageArguments"]]
    assert args == ["--mcp"]


def test_server_json_is_valid_for_the_registry():
    jsonschema = pytest.importorskip("jsonschema")
    schema_file = ROOT / "tests" / "data" / "mcp-server.schema.json"
    server = json.loads((ROOT / "server.json").read_text(encoding="utf-8"))
    jsonschema.validate(server, json.loads(schema_file.read_text(encoding="utf-8")))
