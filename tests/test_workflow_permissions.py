"""Every workflow starts read-only; write access is granted per job (#277, OpenSSF Scorecard Token-Permissions)."""

from pathlib import Path

import pytest
import yaml

WORKFLOW_DIR = Path(__file__).resolve().parents[1] / ".github" / "workflows"
WORKFLOWS = sorted([*WORKFLOW_DIR.glob("*.yml"), *WORKFLOW_DIR.glob("*.yaml")])
READ_ONLY = {"read", "none"}


def read_only(permissions) -> bool:
    """A workflow-level permissions value that grants no write scope."""
    if permissions in ("read-all", {}):
        return True
    return isinstance(permissions, dict) and all(str(v) in READ_ONLY for v in permissions.values())


@pytest.mark.parametrize("text,ok", [
    ("permissions:\n  contents: read\n", True),
    ("permissions: read-all\n", True),
    ("permissions: {}\n", True),
    ("permissions:\n  contents: read\n\n  packages: write\n", False),  # a blank line inside the block
    ('permissions:\n  contents: "write"\n', False),                     # quoted
    ("permissions: {contents: write}\n", False),                         # flow map
    ("permissions: write-all\n", False),
    ("permissions:  # comment\n  contents: read\n", True),
])
def test_the_check_reads_every_yaml_form(text, ok):
    assert read_only(yaml.safe_load(text)["permissions"]) is ok


def test_there_are_workflows():
    assert len(WORKFLOWS) >= 5


@pytest.mark.parametrize("workflow", WORKFLOWS, ids=lambda p: p.name)
def test_every_workflow_is_read_only_at_the_top(workflow):
    data = yaml.safe_load(workflow.read_text(encoding="utf-8"))
    assert "permissions" in data, f"{workflow.name}: no top-level permissions"
    assert read_only(data["permissions"]), f"{workflow.name}: {data['permissions']}"
