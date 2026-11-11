"""The GitHub release of a version shows that version's CHANGELOG section, not a list of pull requests."""

import importlib.util
from pathlib import Path

import yaml

import proxyscraper

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("release_notes", ROOT / ".github" / "scripts" / "release_notes.py")
release_notes = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release_notes)

CHANGELOG = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")


def test_the_current_version_has_its_changelog_section():
    notes = release_notes.section(CHANGELOG, f"v{proxyscraper.__version__}")
    assert notes.startswith("### ")
    assert "## [" not in notes and notes.strip() == notes
    start = CHANGELOG.index(f"## [{proxyscraper.__version__}]")
    assert notes in CHANGELOG[start:CHANGELOG.index("\n## [", start + 1)]


def test_only_the_section_between_its_heading_and_the_next():
    text = ("# Changelog\n\n## [Unreleased]\n\n### Fixed\n- later\n\n## [1.2.0] – 2026-01-02\n\n### Added\n- two\n\n"
            "## [1.1.0] – 2026-01-01\n\n### Added\n- one\n\n[1.2.0]: https://example.org/a\n[1.1.0]: https://example.org/b\n")
    assert release_notes.section(text, "1.2.0") == "### Added\n- two"
    assert release_notes.section(text, "v1.1.0") == "### Added\n- one"  # the link definitions at the end stay out
    assert release_notes.section(text, "1.1") == ""  # no prefix match
    assert release_notes.section(text, "9.9.9") == ""


def test_the_release_workflow_uses_the_notes_and_falls_back_to_generated_ones():
    workflow = yaml.safe_load((ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8"))
    step = next(s for s in workflow["jobs"]["release"]["steps"] if s.get("name") == "Create the GitHub release")
    assert ".github/scripts/release_notes.py" in step["run"]
    assert "--notes-file" in step["run"] and "--generate-notes" in step["run"]
