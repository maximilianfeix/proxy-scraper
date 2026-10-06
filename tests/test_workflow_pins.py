"""Every action a workflow uses is pinned to a commit SHA, with its tag as a comment (#282)."""

import re
from pathlib import Path

import pytest
import yaml

WORKFLOW_DIR = Path(__file__).resolve().parents[1] / ".github" / "workflows"
WORKFLOWS = sorted([*WORKFLOW_DIR.glob("*.yml"), *WORKFLOW_DIR.glob("*.yaml")])
PINNED = re.compile(r"^[\w.-]+/[\w./-]+@[0-9a-f]{40}$")


def uses_of(workflow):
    data = yaml.safe_load(workflow.read_text(encoding="utf-8"))
    for job in (data.get("jobs") or {}).values():
        if "uses" in job:  # a reusable workflow
            yield job["uses"]
        for step in job.get("steps") or []:
            if "uses" in step:
                yield step["uses"]


@pytest.mark.parametrize("workflow", WORKFLOWS, ids=lambda p: p.name)
def test_every_action_is_pinned_to_a_commit(workflow):
    unpinned = [u for u in uses_of(workflow) if not u.startswith("./") and not PINNED.match(u)]
    assert not unpinned, f"{workflow.name}: {unpinned}"


@pytest.mark.parametrize("workflow", WORKFLOWS, ids=lambda p: p.name)
def test_every_pin_says_which_tag_it_is(workflow):
    for line in workflow.read_text(encoding="utf-8").splitlines():
        if re.search(r"uses:\s+\S+@[0-9a-f]{40}", line):
            assert re.search(r"@[0-9a-f]{40} # \S+", line), f"{workflow.name}: {line.strip()}"
