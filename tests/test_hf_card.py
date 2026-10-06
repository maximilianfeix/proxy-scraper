"""The Hugging Face dataset card lives in the repo and documents every field of the snapshots (#271)."""

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from proxyscraper import publish

from .test_publish import run_dir

CARD = Path(__file__).resolve().parents[1] / "docs" / "huggingface" / "README.md"


def card_fields():
    """Field names from the card's field table (first column, in backticks)."""
    return set(re.findall(r"^\| `([a-z0-9_]+)` \|", CARD.read_text(encoding="utf-8"), re.MULTILINE))


def test_the_card_documents_every_field_of_a_snapshot(tmp_path):
    out = tmp_path / "public"
    now = datetime(2026, 9, 24, 18, 0, tzinfo=timezone.utc)
    assert publish.publish(run_dir(tmp_path), out, minimum=2, now=now) == 0
    rows = json.loads((out / "proxies.json").read_text(encoding="utf-8"))
    fields = {key for row in rows for key in row} | {"snapshot_date"}  # the workflow adds snapshot_date
    assert fields - card_fields() == set()


def test_the_card_has_the_metadata_the_hub_needs():
    head = CARD.read_text(encoding="utf-8").split("---")[1]
    assert "license: mit" in head
    assert 'data_files: "data/*/*.parquet"' in head  # the layout the workflow uploads to
    for tag in ("proxies", "networking", "cybersecurity", "web-scraping"):
        assert f"- {tag}" in head


def test_the_workflow_uploads_the_card():
    workflow = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "proxy-list.yml").read_text()
    assert "docs/huggingface/README.md" in workflow
