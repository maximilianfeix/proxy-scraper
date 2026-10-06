"""Every workflow starts read-only; write access is granted per job (#277, OpenSSF Scorecard Token-Permissions)."""

import re
from pathlib import Path

WORKFLOWS = sorted((Path(__file__).resolve().parents[1] / ".github" / "workflows").glob("*.yml"))


def top_level_permissions(text):
    """The workflow-level permissions block (no YAML dependency): the lines under a column-0 `permissions:`."""
    match = re.search(r"^permissions:[ \t]*(\S.*)?\n((?:[ \t]+.*\n)*)", text, re.MULTILINE)
    if not match:
        return None
    if match.group(1):
        return match.group(1).strip()
    return dict(re.findall(r"^[ \t]+([a-z-]+):[ \t]*([a-z-]+)", match.group(2), re.MULTILINE))


def test_there_are_workflows():
    assert len(WORKFLOWS) >= 5


def test_every_workflow_is_read_only_at_the_top():
    for workflow in WORKFLOWS:
        permissions = top_level_permissions(workflow.read_text(encoding="utf-8"))
        assert permissions is not None, f"{workflow.name}: no top-level permissions"
        if isinstance(permissions, str):
            assert permissions == "read-all", workflow.name
        else:
            assert set(permissions.values()) <= {"read", "none"}, f"{workflow.name}: {permissions}"
