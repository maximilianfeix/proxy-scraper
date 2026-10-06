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


def test_every_srcset_candidate_gets_its_own_url():
    assert fix('<img srcset="docs/a.png 1x, docs/b.png 2x">') == \
        f'<img srcset="{RAW}docs/a.png 1x, {RAW}docs/b.png 2x">'


def test_titled_angle_and_reference_links():
    assert fix('[a](docs/a.md "Title")') == f'[a]({BLOB}docs/a.md "Title")'
    assert fix("[a](<docs/a b.md>)") == f"[a](<{BLOB}docs/a b.md>)"
    assert fix("[logo]: docs/logo.png\n[lic]: LICENSE \"MIT\"\n") == \
        f'[logo]: {RAW}docs/logo.png\n[lic]: {BLOB}LICENSE "MIT"\n'


def test_tilde_indented_and_nested_fences_are_left_alone():
    for text in ("~~~\n[x](y)\n~~~\n", "- item\n\n  ```\n  [x](y)\n  ```\n",
                 "````md\n```\n[x](y)\n```\n````\n"):
        assert fix(text) == text, text


def test_inline_code_and_html_comments_are_left_alone():
    text = "Write `[x](y)` like this <!-- see [x](y) --> done"
    assert fix(text) == text


def test_other_schemes_root_relative_and_query_only():
    assert fix("[d](data:image/png;base64,AAAA) [t](tel:123) [q](?tab=x)") == \
        "[d](data:image/png;base64,AAAA) [t](tel:123) [q](?tab=x)"
    assert fix("[a](/docs/a.md)") == f"[a]({BLOB}docs/a.md)"


def test_directories_link_to_the_tree():
    assert fix('<a href="bot/">bot</a>') == f'<a href="https://github.com/{REPO}/tree/v1.26.0/bot/">bot</a>'
