"""Every README links to every other one, and the translations keep the anchors of the English README (#294)."""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
READMES = sorted(p.name for p in ROOT.glob("README*.md"))
# the anchors a condensed translation has to offer, so cross-links from the other READMEs and the website work
SHARED_ANCHORS = ["install", "live-list", "pool-api", "proxy-server", "mcp", "faq"]


def language_bar(name):
    text = (ROOT / name).read_text(encoding="utf-8")
    for line in text.splitlines():
        if "](README" in line and "**" in line and "·" in line:
            return line
    pytest.fail(f"{name} has no language bar")


@pytest.mark.parametrize("name", READMES)
def test_language_bar_links_to_every_other_readme(name):
    bar = language_bar(name)
    linked = set(re.findall(r"\]\((README[^)]*\.md)\)", bar))
    assert linked == set(READMES) - {name}, f"{name}: language bar links {sorted(linked)}"
    assert "**" in bar, f"{name}: the current language should be bold, not a link"


@pytest.mark.parametrize("name", [n for n in READMES if n != "README.md"])
def test_translations_keep_the_shared_anchors(name):
    text = (ROOT / name).read_text(encoding="utf-8")
    missing = [a for a in SHARED_ANCHORS if f'<a id="{a}"></a>' not in text]
    assert not missing, f"{name} lacks anchors {missing}"


@pytest.mark.parametrize("name", [n for n in READMES if n != "README.md"])
def test_translations_use_the_real_commands_and_urls(name):
    text = (ROOT / name).read_text(encoding="utf-8")
    for needle in ("pipx install proxy-scraper-cli", "proxy-scraper-cli[mcp]", "ghcr.io/maximilianfeix/proxy-scraper",
                   "https://maximilianfeix.github.io/proxy-scraper/"):
        assert needle in text, f"{name} lost {needle!r}"
