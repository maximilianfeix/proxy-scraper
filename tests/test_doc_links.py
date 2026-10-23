"""Every relative link in README.md and docs/*.md points to a file that exists, and every #anchor it uses into a
Markdown file of the repo is there – so moving a section out of the README can't silently break a link."""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PAGES = ["README.md", *sorted(str(p.relative_to(ROOT)) for p in (ROOT / "docs").glob("*.md"))]
# anchors that other places link to: the translated READMEs, the website, the server dashboard
README_ANCHORS = ["install", "live-list", "check-states", "mcp", "features", "why-not-just-download-a-list",
                  "examples", "from-python", "proxy-server", "pool-api", "discord-bot", "how-it-works", "output",
                  "recipes", "options", "github-actions", "faq", "who-runs-free-proxies", "roadmap", "contributing",
                  "community", "acknowledgements"]

_FENCE = re.compile(r"^```.*?^```", re.DOTALL | re.MULTILINE)
_CODE = re.compile(r"`[^`\n]*`")
_TARGETS = [re.compile(r"\]\(([^)\s]+)\)"), re.compile(r'(?:src|href)="([^"]+)"'), re.compile(r'srcset="([^"]+)"')]


def _targets(text):
    text = _CODE.sub("", _FENCE.sub("", text))
    for pattern in _TARGETS:
        for match in pattern.findall(text):
            for candidate in match.split(","):
                yield candidate.strip().split(" ")[0]


def _slug(heading):
    return re.sub(r"[^\w\- ]", "", heading.strip().lower()).replace(" ", "-")


def _anchors(path):
    text = path.read_text(encoding="utf-8")
    ids = set(re.findall(r'<a id="([^"]+)"></a>', text))
    ids |= {_slug(h) for h in re.findall(r"^#{1,6} (.+)$", _FENCE.sub("", text), re.MULTILINE)}
    return ids


@pytest.mark.parametrize("page", PAGES)
def test_relative_links_resolve(page):
    source = ROOT / page
    # GitHub serves a file at /<owner>/<repo>/blob/<ref>/<path>, so "../../" from the root (one more per folder)
    # reaches the repo's own pages: issues, releases, actions, the proxy-list branch
    github_route = "../" * (len(Path(page).parts) + 1)
    broken = []
    for target in _targets(source.read_text(encoding="utf-8")):
        if re.match(r"^([a-zA-Z][a-zA-Z0-9+.-]*:|//)", target):
            continue
        if target.startswith(github_route) and not target.startswith(github_route + "../"):
            continue
        path, _, anchor = target.partition("#")
        resolved = (source.parent / path).resolve() if path else source
        try:
            resolved.relative_to(ROOT)
        except ValueError:
            broken.append(target)  # leaves the repo without being one of GitHub's pages
            continue
        if not resolved.exists() or (anchor and resolved.suffix == ".md" and anchor not in _anchors(resolved)):
            broken.append(target)
    assert not broken, f"{page}: broken links {broken}"


def test_the_readme_keeps_the_anchors_others_link_to():
    missing = [a for a in README_ANCHORS if f'<a id="{a}"></a>' not in (ROOT / "README.md").read_text(encoding="utf-8")]
    assert not missing, f"README.md lost anchors {missing}"
