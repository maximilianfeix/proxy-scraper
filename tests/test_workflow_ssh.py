"""SSH from the workflows never trusts a host key on first use (accept-new): every host is pinned."""

import base64
import hashlib
import re
from pathlib import Path

import pytest

WORKFLOW_DIR = Path(__file__).resolve().parents[1] / ".github" / "workflows"
WORKFLOWS = sorted([*WORKFLOW_DIR.glob("*.yml"), *WORKFLOW_DIR.glob("*.yaml")])
# docs.github.com: "GitHub's SSH key fingerprints"
GITHUB_FINGERPRINTS = {
    "ssh-ed25519": "+DiY3wvvV6TuJJhbpZisF/zLDA0zPMSvHdkr4UvCOqU",
    "ecdsa-sha2-nistp256": "p2QAMXNIC1TJYWeIOttrVc98/R1BUFWu3/LiyKgUfQM",
    "ssh-rsa": "uNiVztksCsDhcc0u9e8BujQXVUpKZIDTMczCvj3tD2s",
}


@pytest.mark.parametrize("workflow", WORKFLOWS, ids=lambda p: p.name)
def test_no_workflow_trusts_an_unknown_host_key(workflow):
    text = workflow.read_text(encoding="utf-8")
    assert not re.search(r"StrictHostKeyChecking=(accept-new|no|off)", text, re.IGNORECASE)


def test_the_list_repository_push_pins_githubs_published_host_keys():
    text = (WORKFLOW_DIR / "proxy-list.yml").read_text(encoding="utf-8")
    assert "StrictHostKeyChecking=yes -o UserKnownHostsFile=$HOME/.ssh/github_known_hosts" in text
    keys = re.findall(r"^\s*github\.com (\S+) (\S+)$", text, re.MULTILINE)
    fingerprints = {kind: base64.b64encode(hashlib.sha256(base64.b64decode(blob)).digest()).decode().rstrip("=")
                    for kind, blob in keys}
    assert fingerprints == GITHUB_FINGERPRINTS
