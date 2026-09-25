import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture(autouse=True)
def offline_blocklist(monkeypatch):
    """Tests stay offline: the blocklist resolver answers nothing, so the probe marks it unusable."""
    from proxyscraper import blocklist

    async def nothing(name):
        return None
    monkeypatch.setattr(blocklist, "system_resolve", nothing)
    monkeypatch.setattr(blocklist.Blocklist.__init__, "__defaults__", (nothing, blocklist.ZONE))
