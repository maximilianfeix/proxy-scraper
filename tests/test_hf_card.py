"""The Hugging Face dataset card lives in the repo and documents every field of the snapshots (#271)."""

from pathlib import Path

CARD = Path(__file__).resolve().parents[1] / "docs" / "huggingface" / "README.md"


def test_the_card_has_the_metadata_the_hub_needs():
    head = CARD.read_text(encoding="utf-8").split("---")[1]
    assert "license: mit" in head
    assert 'data_files: "data/*/*.parquet"' in head  # the layout the workflow uploads to
    for tag in ("proxies", "networking", "cybersecurity", "web-scraping"):
        assert f"- {tag}" in head


def test_the_workflow_uploads_the_card():
    workflow = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "proxy-list.yml").read_text()
    assert "docs/huggingface/README.md" in workflow
