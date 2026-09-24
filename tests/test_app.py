import asyncio
import json

import pytest

from proxyscraper import app


@pytest.mark.parametrize("status, body, expected", [
    (200, json.dumps({"origin": "5.5.5.5", "headers": {}}).encode(), "34.1.2.3"),
    (301, b"", None),                                              # Redirect auf HTTPS
    (200, b"<html>Bitte im WLAN anmelden</html>", None),           # Captive Portal
    (200, json.dumps({"origin": "unbekannt"}).encode(), None),
])
def test_confirm_target_requires_the_exact_expected_answer(monkeypatch, status, body, expected):
    async def fake_request(url, timeout, max_redirects):
        assert max_redirects == 0  # genau wie die Bestätigung selbst: keinem Redirect folgen
        return status, {}, body

    async def go():
        loop = asyncio.get_running_loop()

        async def fake_getaddrinfo(*args, **kwargs):
            return [(None, None, None, "", ("34.1.2.3", 80))]

        monkeypatch.setattr(loop, "getaddrinfo", fake_getaddrinfo)
        return await app.confirm_target()

    monkeypatch.setattr(app, "http_request", fake_request)
    assert asyncio.run(go()) == expected


def test_confirm_target_unreachable(monkeypatch):
    async def fail(*args, **kwargs):
        raise ConnectionError("blockiert")

    monkeypatch.setattr(app, "http_request", fail)
    assert asyncio.run(app.confirm_target()) is None
