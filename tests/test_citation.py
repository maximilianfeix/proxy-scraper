"""CITATION.cff gives the repo GitHub's "Cite this repository" button (#275)."""

import re
from pathlib import Path

CFF = (Path(__file__).resolve().parents[1] / "CITATION.cff").read_text(encoding="utf-8")


def top_level(key):
    match = re.search(rf"^{re.escape(key)}:\s*(.*)$", CFF, re.MULTILINE)
    return match and match.group(1).strip().strip('"')


def test_citation_has_what_github_needs():
    assert top_level("cff-version") == "1.2.0"
    assert top_level("title") and top_level("message")
    assert re.search(r"^authors:\n  - family-names: \S", CFF, re.MULTILINE)
    assert top_level("license") == "MIT"
    assert top_level("repository-code") == "https://github.com/maximilianfeix/proxy-scraper"


def test_citation_has_no_version_that_would_go_stale():
    assert top_level("version") is None and top_level("date-released") is None
