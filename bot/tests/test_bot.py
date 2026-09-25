"""Bot logic without a Discord connection: parsing the live list, filters, messages, state."""

import json
import random
from datetime import datetime, timezone

import discord
import pytest
from proxybot import layout, messages
from proxybot.config import Settings
from proxybot.feed import Proxy, parse_snapshot, pick_one, select, table
from proxybot.state import State

STATS = {"updated": "2026-09-25T12:40:56+00:00", "total": 4, "by_type": {"http": 2, "socks4": 1, "socks5": 1},
         "https": 2, "elite": 3, "median_latency": 2119, "countries": {"US": 2, "DE": 1, "NL": 1}}
ROWS = [
    {"ptype": "http", "proxy": "1.1.1.1:80", "latency": 900, "country": "US", "https": True, "anonymity": "elite"},
    {"ptype": "socks5", "proxy": "2.2.2.2:1080", "latency": 120, "country": "DE", "https": True,
     "anonymity": "elite", "hosting": True, "org": "DigitalOcean, LLC", "streak": 5, "blocklisted": True},
    {"ptype": "socks4", "proxy": "3.3.3.3:4145", "latency": 400, "country": "NL", "anonymity": "elite"},
    {"ptype": "http", "proxy": "4.4.4.4:3128", "latency": 3000, "country": "US", "anonymity": "anonymous"},
    {"ptype": "ftp", "proxy": "5.5.5.5:21", "latency": 1},             # unknown type
    {"ptype": "http", "proxy": "", "latency": 1},                      # no address
    {"ptype": "http", "proxy": "6.6.6.6:80", "latency": "slow"},       # broken latency
    "not even a dict",
]
HISTORY = [{"updated": "2026-09-25T06:00:00+00:00", "total": 3}, {"updated": STATS["updated"], "total": 4}]


@pytest.fixture
def snap():
    return parse_snapshot(STATS, ROWS, HISTORY)


def test_parse_skips_broken_rows_and_sorts_by_latency(snap):
    assert [p.address for p in snap.proxies] == ["2.2.2.2:1080", "3.3.3.3:4145", "1.1.1.1:80", "4.4.4.4:3128"]
    assert snap.updated == datetime(2026, 9, 25, 12, 40, 56, tzinfo=timezone.utc)
    assert snap.previous_total() == 3  # the run before, not this one


def test_filters(snap):
    assert [p.address for p in select(snap.proxies, ptype="http")] == ["1.1.1.1:80", "4.4.4.4:3128"]
    assert [p.address for p in select(snap.proxies, country=" us ")] == ["1.1.1.1:80", "4.4.4.4:3128"]
    assert [p.address for p in select(snap.proxies, https=True, no_datacenter=True)] == ["1.1.1.1:80"]
    assert [p.address for p in select(snap.proxies, elite=True, max_latency=500)] == ["2.2.2.2:1080", "3.3.3.3:4145"]
    assert [p.address for p in select(snap.proxies, stable=True)] == ["2.2.2.2:1080"]


def test_pick_one_takes_one_of_the_fastest(snap):
    assert pick_one([], random.Random(1)) is None
    many = [Proxy("http", f"9.9.9.{i}:80", i) for i in range(100)]
    picks = {pick_one(many, random.Random(seed)).latency for seed in range(50)}
    assert max(picks) < 20 and len(picks) > 1


def test_table_is_aligned(snap):
    lines = table(snap.proxies, 3).splitlines()
    assert len(lines) == 3 and lines[0].startswith("socks5://2.2.2.2:1080")
    assert len({line.index(" ms") for line in lines}) == 1  # latency column lines up
    assert table([], 5) == "no matching proxy"


def test_messages_stay_within_discord_limits(snap):
    many = [Proxy("socks4", f"255.255.255.{i}:65535", 99999, "US", True, "anonymous") for i in range(200)]
    big = parse_snapshot(dict(STATS, total=200), [vars(p) | {"proxy": p.address} for p in many])
    for embed in (messages.summary(snap), messages.summary(big), messages.type_post(big, "socks4"),
                  messages.results(big.proxies, 25, "socks4"), messages.stats(snap), messages.about()):
        assert len(embed) <= 6000 and len(embed.description or "") <= 4096
        assert all(len(f.value) <= 1024 for f in embed.fields)


def test_summary_shows_the_trend(snap):
    embed = messages.summary(snap)
    assert embed.title == "4 working proxies" and "+1 since the last run" in embed.description
    assert embed.timestamp == snap.updated


def test_results_and_single(snap):
    assert messages.results([], 10, "DE").title == "No matching proxy"
    assert "attached" in messages.results(snap.proxies, 2, "none").description
    one = messages.single(snap.proxies[0])
    assert one.title == "socks5://2.2.2.2:1080"
    assert any("socks5h://2.2.2.2:1080" in f.value for f in one.fields)  # DNS through the proxy
    assert any("datacenter" in f.value for f in one.fields)


def test_text_file_is_all_txt_format(snap):
    file = messages.text_file(snap.proxies[:2], "all.txt")
    assert file.filename == "all.txt"
    assert file.fp.read().decode() == "socks5://2.2.2.2:1080\nsocks4://3.3.3.3:4145\n"


def test_state_survives_restarts_and_broken_files(tmp_path):
    path = tmp_path / "state" / "state.json"
    state = State(path)
    assert state.is_new(1, "run-a")
    state.mark(1, "run-a")
    again = State(path)
    assert not again.is_new(1, "run-a") and again.is_new(1, "run-b") and again.is_new(2, "run-a")
    path.write_text("{broken", encoding="utf-8")
    assert State(path).is_new(1, "run-a")
    path.write_text(json.dumps({"posted": "not a dict"}), encoding="utf-8")
    assert State(path).posted == {}


def test_settings_need_a_token(monkeypatch):
    monkeypatch.delenv("DISCORD_TOKEN", raising=False)
    with pytest.raises(SystemExit):
        Settings.from_env()
    monkeypatch.setenv("DISCORD_TOKEN", " abc ")
    monkeypatch.setenv("PROXYBOT_POLL_SECONDS", "5")
    monkeypatch.setenv("PROXYBOT_FEED_URL", "https://example.org/list/")
    settings = Settings.from_env()
    assert settings.token == "abc" and settings.poll_seconds == 60 and settings.feed_url == "https://example.org/list"


def test_layout_has_one_writable_channel():
    names = [c.name for c in layout.CHANNELS]
    assert len(names) == len(set(names))
    assert {"live-feed", "http", "socks4", "socks5", "about"} <= set(names)
    assert [c.name for c in layout.CHANNELS if not c.read_only] == ["commands"]
    assert all(len(c.topic) <= 1024 for c in layout.CHANNELS)


def test_about_mentions_every_channel_and_command():
    text = str(messages.about().to_dict())
    for name in [c.name for c in layout.CHANNELS if c.name != "about"] + ["/proxies", "/proxy", "/stats"]:
        assert name in text, name
    assert isinstance(messages.LIME, int) and discord.Colour(messages.LIME)


class FakeChannel:
    def __init__(self, name, fail=False):
        self.name, self.fail, self.sent = name, fail, []
        self.category = type("Category", (), {"name": layout.CATEGORY})()

    async def send(self, **kwargs):
        if self.fail:
            raise discord.HTTPException(type("Response", (), {"status": 403, "reason": "Forbidden"})(), "no")
        self.sent.append(kwargs)

    def history(self, limit=50):
        async def empty():
            return
            yield
        return empty()


def test_a_broken_protocol_channel_does_not_repeat_the_summary(tmp_path, snap):
    import asyncio

    from proxybot.bot import ProxyBot

    async def go():
        bot = ProxyBot(Settings(token="x", state_file=tmp_path / "state.json"))
        bot._post_lock = asyncio.Lock()
        channels = [FakeChannel("live-feed"), FakeChannel("http"), FakeChannel("socks4", fail=True),
                    FakeChannel("socks5")]
        guild = type("Guild", (), {"id": 1, "name": "test", "text_channels": channels, "me": object()})()
        await bot.post_run(guild, snap)
        await bot.post_run(guild, snap)  # the next poll with the same run
        return channels

    feed, http, _, socks5 = asyncio.run(go())
    assert len(feed.sent) == 1                      # summary once, not on every poll
    assert len(http.sent) == 1 and len(socks5.sent) == 1  # the other channels still got their list


def test_blocklist_filter_and_unknown_values(snap):
    assert snap.proxies[0].blocklisted is True and snap.proxies[1].blocklisted is None
    assert "2.2.2.2:1080" not in [p.address for p in select(snap.proxies, not_blocklisted=True)]
    assert len(select(snap.proxies, not_blocklisted=True)) == 3  # unknown ones stay
    weird = Proxy.from_row({"ptype": "http", "proxy": "7.7.7.7:80", "latency": 5, "blocklisted": "yes"})
    assert weird.blocklisted is None
    one = messages.single(snap.proxies[0])
    assert any(f.name == "Blocklist" and f.value == "on SpamCop" for f in one.fields)
