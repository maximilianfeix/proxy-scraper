import asyncio

import pytest

from proxyscraper import app


@pytest.mark.parametrize("probe_ok, expected", [(True, "34.1.2.3"), (False, None)])
def test_confirm_target_probes_the_resolved_ip(monkeypatch, probe_ok, expected):
    probed = []

    async def fake_probe(ip, timeout):
        probed.append(ip)
        return probe_ok

    async def go():
        loop = asyncio.get_running_loop()

        async def fake_getaddrinfo(*args, **kwargs):
            return [(None, None, None, "", ("34.1.2.3", 80))]

        monkeypatch.setattr(loop, "getaddrinfo", fake_getaddrinfo)
        return await app.confirm_target()

    monkeypatch.setattr(app, "probe_confirm_target", fake_probe)
    assert asyncio.run(go()) == expected
    assert probed == ["34.1.2.3"]  # genau die IP, die später benutzt wird


def test_confirm_target_unresolvable(monkeypatch):
    async def go():
        loop = asyncio.get_running_loop()

        async def fail(*args, **kwargs):
            raise OSError("keine Namensauflösung")

        monkeypatch.setattr(loop, "getaddrinfo", fail)
        return await app.confirm_target()

    assert asyncio.run(go()) is None


@pytest.mark.parametrize("found, fakes, expected", [
    (0, 0, True),      # nichts kommt durch -> Firewall
    (1, 0, True),
    (0, 50, False),    # Honeypots bestehen die Basisprüfung -> Verbindungen klappen
    (30, 0, False),
])
def test_network_blocked_counts_fakes_as_reachable(found, fakes, expected):
    from proxyscraper.ui import LiveStats

    stats = LiveStats({"http": 10000})
    stats.checked = 10000
    stats.working_by_type["http"] = found
    stats.fakes = fakes
    assert app.is_network_blocked(stats) is expected
