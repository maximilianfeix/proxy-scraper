"""The README on PyPI gets absolute image and link URLs, so nothing is broken there (#280)."""

import importlib.util
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("pypi_readme", ROOT / ".github" / "scripts" / "pypi_readme.py")
pypi_readme = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pypi_readme)

REPO = "maximilianfeix/proxy-scraper"
RAW = f"https://raw.githubusercontent.com/{REPO}/v1.26.0/"
BLOB = f"https://github.com/{REPO}/blob/v1.26.0/"


def fix(text):
    return pypi_readme.absolutize(text, REPO, "v1.26.0")


def test_images_point_at_the_raw_file_of_the_tag():
    assert fix('<img src="docs/demo.svg" alt="Demo">') == f'<img src="{RAW}docs/demo.svg" alt="Demo">'
    assert fix('<source media="(x)" srcset="docs/banner-dark.svg">') == \
        f'<source media="(x)" srcset="{RAW}docs/banner-dark.svg">'
    assert fix("![chart](docs/summary.svg)") == f"![chart]({RAW}docs/summary.svg)"


def test_links_point_at_github():
    assert fix("[MIT](LICENSE)") == f"[MIT]({BLOB}LICENSE)"
    assert fix("[zh](README.zh-CN.md)") == f"[zh]({BLOB}README.zh-CN.md)"
    assert fix('<a href="bot/">bot</a>') == f'<a href="{BLOB}bot/">bot</a>'
    assert fix("[list](../../tree/proxy-list)") == f"[list](https://github.com/{REPO}/tree/proxy-list)"
    assert fix("[ci](../../actions/workflows/tests.yml)") == f"[ci](https://github.com/{REPO}/actions/workflows/tests.yml)"


def test_absolute_links_anchors_and_mail_stay():
    text = ("[a](https://example.com) [b](#install) [c](mailto:x@y.z) "
            '<img src="https://img.shields.io/x"> <a href="#faq">faq</a>')
    assert fix(text) == text


def test_code_blocks_are_left_alone():
    text = "```bash\ncurl -O docs/demo.svg\n[not](a-link)\n```\n"
    assert fix(text) == text


def test_the_real_readme_keeps_no_relative_image_or_link():
    fixed = fix((ROOT / "README.md").read_text(encoding="utf-8"))
    prose = re.sub(r"```.*?```", "", fixed, flags=re.DOTALL)
    assert not re.findall(r'(?:src|srcset|href)="(?!https?://|#|mailto:)[^"]+"', prose)
    assert not re.findall(r"\]\((?!https?://|#|mailto:)[^)\s]+\)", prose)


def test_the_release_builds_with_the_fixed_readme():
    release = (ROOT / ".github" / "workflows" / "release.yml").read_text()
    fix_at = release.index(".github/scripts/pypi_readme.py")
    assert fix_at < release.index("python -m build")
