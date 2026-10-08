"""Makes the README's relative image and link paths absolute for PyPI, which can't resolve them (#280).

The release workflow runs this on the checked-out README right before `python -m build`; the README in the
repo stays as it is. Images go to raw.githubusercontent.com (served as image/svg+xml and image/png, which
PyPI's image proxy accepts), directories to github.com/<repo>/tree/<tag>/, other files to
github.com/<repo>/blob/<tag>/, and `../../x` to github.com/<repo>/x. Code blocks, inline code and HTML
comments are left alone, so examples show exactly what they say.

    python .github/scripts/pypi_readme.py README.md maximilianfeix/proxy-scraper v1.26.0
"""

import posixpath
import re
import sys

IMAGE_SUFFIXES = (".svg", ".png", ".gif", ".jpg", ".jpeg", ".webp")
_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
# CommonMark: a fence is indented by at most 3 spaces, and a backtick fence's info string has no backtick
_FENCE_OPEN = re.compile(r"^ {0,3}(`{3,}(?=[^`\n]*$)|~{3,})")
# inline code spans (closed by the same run of backticks, never across a blank line) and HTML comments
_LITERAL = re.compile(r"(`+)(?:(?!\n[ \t]*\n).)*?(?<!`)\1(?!`)|<!--.*?-->", re.DOTALL)
_ATTR = re.compile(r'(?<![\w-])(src|href)="([^"]+)"')
_SRCSET = re.compile(r'(?<![\w-])srcset="([^"]+)"')
_MD_INLINE = re.compile(r'\]\(([ \t]*)(<[^>\n]*>|[^)\s]+)((?:[ \t]+"[^"\n]*")?[ \t]*)\)')
# reference definitions, not footnotes ([^1]: …)
_MD_REFERENCE = re.compile(r'^([ \t]{0,3}\[(?!\^)[^\]\n]+\]:[ \t]*)(<[^>\n]*>|\S+)', re.MULTILINE)


def _absolute(target: str, repo: str, ref: str) -> str:
    if target.startswith(("//", "#", "?")) or _SCHEME.match(target):
        return target
    if target.startswith("../../"):
        return f"https://github.com/{repo}/{target[len('../../'):]}"
    path = target.lstrip("/")
    tail = "/" if path.endswith("/") else ""
    path = posixpath.normpath(path) + tail if path not in ("", ".", "./") else ""
    if path.startswith(".."):
        return target  # leaves the repo – the check below reports it
    bare = path.split("#")[0].split("?")[0]
    if bare.lower().endswith(IMAGE_SUFFIXES):
        return f"https://raw.githubusercontent.com/{repo}/{ref}/{path}"
    kind = "tree" if bare.endswith("/") or not bare else "blob"
    return f"https://github.com/{repo}/{kind}/{ref}/{path}"


def _target(target: str, repo: str, ref: str) -> str:
    """A link target as written, possibly in <angle brackets>."""
    if target.startswith("<") and target.endswith(">"):
        return f"<{_absolute(target[1:-1], repo, ref)}>"
    return _absolute(target, repo, ref)


def _srcset(value: str, repo: str, ref: str) -> str:
    candidates = []
    for candidate in filter(None, (c.strip() for c in value.split(","))):
        url, _, descriptor = candidate.partition(" ")
        candidates.append(f"{_absolute(url, repo, ref)} {descriptor}".strip())
    return ", ".join(candidates)


def _prose(text: str, repo: str, ref: str) -> str:
    text = _ATTR.sub(lambda m: f'{m.group(1)}="{_absolute(m.group(2), repo, ref)}"', text)
    text = _SRCSET.sub(lambda m: f'srcset="{_srcset(m.group(1), repo, ref)}"', text)
    return _MD_INLINE.sub(lambda m: f"]({m.group(1)}{_target(m.group(2), repo, ref)}{m.group(3)})", text)


def _references(text: str, repo: str, ref: str) -> str:
    """Reference definitions at a real line start – not inside or right after inline code."""
    literals = [m.span() for m in _LITERAL.finditer(text)]

    def replace(match):
        if any(start <= match.start() < end for start, end in literals):
            return match.group(0)
        return f"{match.group(1)}{_target(match.group(2), repo, ref)}"

    return _MD_REFERENCE.sub(replace, text)


def _outside_literals(text: str, repo: str, ref: str) -> str:
    text = _references(text, repo, ref)
    out, last = [], 0
    for match in _LITERAL.finditer(text):
        out.append(_prose(text[last:match.start()], repo, ref))
        out.append(match.group(0))
        last = match.end()
    out.append(_prose(text[last:], repo, ref))
    return "".join(out)


def absolutize(text: str, repo: str, ref: str) -> str:
    """README text -> the same text with absolute URLs, code and comments untouched."""
    out, prose, fence = [], [], None
    text = text.replace("\r\n", "\n")
    for line in text.splitlines(keepends=True):
        if fence is None:
            opened = _FENCE_OPEN.match(line)
            if opened:
                out.append(_outside_literals("".join(prose), repo, ref))
                prose, fence = [], opened.group(1)
                out.append(line)
            else:
                prose.append(line)
        else:
            out.append(line)
            # closed by a run of the same character at least as long, with nothing else on the line
            if re.fullmatch(rf" {{0,3}}{re.escape(fence[0])}{{{len(fence)},}}[ \t]*\n?", line):
                fence = None
    out.append(_outside_literals("".join(prose), repo, ref))
    return "".join(out)


_HTML_URL = re.compile(r'(?<![\w-])(?:src|href)="([^"]+)"|(?<![\w-])srcset="([^"]+)"')


def _is_relative(url: str) -> bool:
    return not (url.startswith(("//", "#", "?")) or _SCHEME.match(url))


def relative_targets(text: str) -> list:
    """Image and link targets that are still relative, as a Markdown renderer sees them (needs markdown-it-py).

    The rewrite above works with regular expressions; this check parses the result the way PyPI does, so a
    case the rewrite gets wrong fails the release instead of reaching pypi.org."""
    from markdown_it import MarkdownIt

    found = []
    html = MarkdownIt("commonmark", {"html": True}).enable("table").render(text)
    for single, srcset in _HTML_URL.findall(html):
        urls = [single] if single else [c.split()[0] for c in srcset.split(",") if c.strip()]
        found += [url for url in urls if _is_relative(url)]
    return found


if __name__ == "__main__":
    path, repo, ref = sys.argv[1:]
    with open(path, encoding="utf-8") as handle:
        text = absolutize(handle.read(), repo, ref)
    left = relative_targets(text)
    if left:
        sys.exit(f"{path}: still relative after the rewrite, would break on PyPI: {left}")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    print(f"{path}: relative paths now point at {repo}@{ref}")
