"""Telegram bot logic without a Telegram connection: commands, filters, answers."""

import contextlib
import random

import pytest
from proxybot import telegram
from proxybot.feed import parse_snapshot
from test_bot import HISTORY, ROWS, STATS


@pytest.fixture
def snap():
    return parse_snapshot(STATS, ROWS, HISTORY)


@pytest.mark.parametrize("text, expected", [
    ("/proxy", ("proxy", [])),
    ("/proxy de socks5", ("proxy", ["de", "socks5"])),
    ("/proxies@ProxyScraperBot 5 us", ("proxies", ["5", "us"])),  # commands in groups carry the bot's name
    ("/PROXY", ("proxy", [])),
    ("/proxy@SomeOtherBot", None),     # meant for another bot in the group
    ("/ban someone", None),            # not one of ours: stay quiet
    ("hello", None),
    ("", None),
])
def test_commands(text, expected):
    assert telegram.parse_command(text, me="ProxyScraperBot") == expected


def test_filters_from_free_words():
    assert telegram.parse_filters(["de", "socks5", "https", "7"]) == {"country": "DE", "ptype": "socks5",
                                                                        "https": True, "count": 7}
    assert telegram.parse_filters(["999"])["count"] == telegram.MAX_LIST  # capped
    assert telegram.parse_filters(["what"]) is None  # unknown words: say how it works instead of guessing
    assert telegram.parse_filters(["\u00b2"]) is None  # "²" passes str.isdigit(), int() can't read it


def test_one_proxy_with_a_curl_line(snap):
    text = telegram.reply("proxy", ["de"], snap, random.Random(1))
    assert "socks5://2.2.2.2:1080" in text and "curl -x socks5h://2.2.2.2:1080" in text
    assert "<code>" in text  # tap to copy in Telegram


def test_a_short_list_fastest_first(snap):
    text = telegram.reply("proxies", ["us", "2"], snap)
    assert text.index("1.1.1.1:80") < text.index("4.4.4.4:3128")
    assert text.count("://") == 2


def test_nothing_matching_says_what_to_try(snap):
    text = telegram.reply("proxy", ["jp"], snap)
    assert "No proxy" in text and "/proxy" in text


def test_stats_and_help(snap):
    assert "4 working proxies" in telegram.reply("stats", [], snap)
    for cmd in ("start", "help"):
        assert "/proxy" in telegram.reply(cmd, [], snap)


def test_no_list_yet():
    assert "not loaded" in telegram.reply("proxy", [], None)


def test_user_text_is_escaped(snap):
    text = telegram.reply("proxies", ["<b>"], snap)
    assert "<code>&lt;b&gt;</code>" in text and "<code><b></code>" not in text


def test_a_message_gets_an_answer_in_the_same_chat(snap):
    import asyncio

    sent = []

    class Bot(telegram.TelegramBot):
        async def call(self, method, **params):
            sent.append((method, params))

    bot = Bot("token", session=None)
    bot.snapshot = snap
    asyncio.run(bot.handle({"update_id": 1, "message": {"text": "/proxies us", "chat": {"id": 42}}}))
    asyncio.run(bot.handle({"update_id": 2, "message": {"text": "just chatting", "chat": {"id": 42}}}))
    assert len(sent) == 1  # plain messages in a group get no answer
    method, params = sent[0]
    assert method == "sendMessage" and params["chat_id"] == 42 and params["parse_mode"] == "HTML"
    assert "1.1.1.1:80" in params["text"]


def test_telegram_alone_is_enough(monkeypatch):
    from proxybot.config import Settings
    monkeypatch.delenv("DISCORD_TOKEN", raising=False)
    monkeypatch.setenv("TELEGRAM_TOKEN", "123:abc")
    settings = Settings.from_env()
    assert settings.telegram_token == "123:abc" and settings.token == ""


def test_one_bot_failing_leaves_the_other_running(monkeypatch):
    import asyncio

    from proxybot import __main__ as entry

    monkeypatch.setattr(entry, "RESTART_AFTER", 0.01)
    runs = {"broken": 0, "fine": 0}

    async def broken():
        runs["broken"] += 1
        raise RuntimeError("setMyCommands: Unauthorized")

    async def fine():
        runs["fine"] += 1
        await asyncio.sleep(0.2)

    async def go():
        await asyncio.wait_for(asyncio.gather(entry.supervised("telegram", broken), entry.supervised("discord", fine),
                                              return_exceptions=True), 0.1)
    with contextlib.suppress(asyncio.TimeoutError):
        asyncio.run(go())
    assert runs["broken"] > 1 and runs["fine"] == 1  # the broken one keeps being retried, the other one never stopped
