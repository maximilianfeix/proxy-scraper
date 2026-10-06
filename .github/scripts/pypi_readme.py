"""Makes the README's relative image and link paths absolute for PyPI, which can't resolve them (#280).

The release workflow runs this on the checked-out README right before `python -m build`; the README in the
repo stays as it is. Images go to raw.githubusercontent.com (served as image/svg+xml and image/png, which
PyPI's image proxy accepts), other files to github.com/<repo>/blob/<tag>/, and `../../x` to github.com/<repo>/x.
Fenced code blocks are left alone.

    python .github/scripts/pypi_readme.py README.md maximilianfeix/proxy-scraper v1.26.0
"""

import re
import sys

IMAGE_SUFFIXES = (".svg", ".png", ".gif", ".jpg", ".jpeg", ".webp")
_FENCE = re.compile(r"(^```.*?^```[^\n]*$)", re.MULTILINE | re.DOTALL)
_ATTR = re.compile(r'\b(src|srcset|href)="([^"]+)"')
_MD_TARGET = re.compile(r"\]\(([^)\s]+)\)")


def _absolute(target: str, repo: str, ref: str) -> str:
    if target.startswith(("http://", "https://", "//", "#", "mailto:")):
        return target
    if target.startswith("../../"):
        return f"https://github.com/{repo}/{target[len('../../'):]}"
    path = target[2:] if target.startswith("./") else target
    if path.split("#")[0].split("?")[0].lower().endswith(IMAGE_SUFFIXES):
        return f"https://raw.githubusercontent.com/{repo}/{ref}/{path}"
    return f"https://github.com/{repo}/blob/{ref}/{path}"


def _prose(text: str, repo: str, ref: str) -> str:
    text = _ATTR.sub(lambda m: f'{m.group(1)}="{_absolute(m.group(2), repo, ref)}"', text)
    return _MD_TARGET.sub(lambda m: f"]({_absolute(m.group(1), repo, ref)})", text)


def absolutize(text: str, repo: str, ref: str) -> str:
    """README text -> the same text with absolute URLs outside fenced code blocks."""
    parts = _FENCE.split(text)
    # split() with one group: even indexes are prose, odd ones the code blocks
    return "".join(part if i % 2 else _prose(part, repo, ref) for i, part in enumerate(parts))


if __name__ == "__main__":
    path, repo, ref = sys.argv[1:]
    with open(path, encoding="utf-8") as handle:
        text = handle.read()
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(absolutize(text, repo, ref))
    print(f"{path}: relative paths now point at {repo}@{ref}")
