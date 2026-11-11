"""Prints one version's section of CHANGELOG.md, for the notes of its GitHub release.

The section runs from its "## [X.Y.Z]" heading to the next "## [" heading (or the link definitions at the end of
the file); the heading itself is left out. Prints nothing for a version without a section – the release workflow
then falls back to GitHub's generated notes.

    python .github/scripts/release_notes.py CHANGELOG.md v1.33.0 > notes.md
"""

import re
import sys

_LINK_DEFINITION = re.compile(r"^\[[^\]\n]+\]:\s")


def section(changelog: str, version: str) -> str:
    version = version.removeprefix("v")
    lines = changelog.splitlines()
    start = next((i for i, line in enumerate(lines) if re.match(rf"## \[{re.escape(version)}\](?!\S)", line)), None)
    if start is None:
        return ""
    body = []
    for line in lines[start + 1:]:
        if line.startswith("## [") or _LINK_DEFINITION.match(line):
            break
        body.append(line)
    return "\n".join(body).strip()


def main(argv) -> int:
    if len(argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    with open(argv[1], encoding="utf-8") as fh:
        notes = section(fh.read(), argv[2])
    if notes:
        print(notes)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
