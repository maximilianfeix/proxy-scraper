"""Readiness and refused tokens: what deploy/install.sh relies on to tell a working release from a running one."""

import asyncio
import os

import discord
import pytest
from proxybot import __main__ as entry
from proxybot import telegram
from proxybot.config import Settings


class FakeTelegram(telegram.TelegramBot):
    """Answers from a table {method: result or TelegramError} instead of the Bot API."""

    def __init__(self, answers, ready=None):
        super().__init__("token", session=None, ready=ready)
        self.answers = answers
        self.calls = []

    async def call(self, method, **params):
        self.calls.append(method)
        answer = self.answers.get(method, True)
        if isinstance(answer, Exception):
            raise answer
        if method == "getUpdates":
            raise asyncio.CancelledError  # the first poll ends the test
        return answer


def test_the_ready_file_holds_the_pid_once_every_bot_logged_in(tmp_path):
    path = tmp_path / "ready"
    path.write_text("12345\n")  # left over from the process before
    readiness = entry.Readiness(path, ["telegram", "discord"])
    assert not path.exists()
    readiness.mark("telegram")
    assert not path.exists()  # Discord isn't logged in yet
    readiness.mark("discord")
    assert path.read_text() == f"{os.getpid()}\n"
    readiness.mark("discord")  # on_ready again after a reconnect: harmless
    assert path.read_text() == f"{os.getpid()}\n"


def test_without_a_ready_file_nothing_is_written(tmp_path, monkeypatch):
    monkeypatch.delenv("PROXYBOT_READY_FILE", raising=False)
    assert entry.ready_file() is None
    entry.Readiness(None, ["discord"]).mark("discord")  # must not fail
    monkeypatch.setenv("PROXYBOT_READY_FILE", str(tmp_path / "ready"))
    assert entry.ready_file() == tmp_path / "ready"


def test_telegram_is_ready_after_getme():
    marked = []
    bot = FakeTelegram({"getMe": {"username": "ProxyScraperBot"}}, ready=lambda: marked.append(1))
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(bot.run())
    assert marked == [1] and bot.me == "ProxyScraperBot"


@pytest.mark.parametrize("code", [401, 403, 404])
def test_a_refused_telegram_token_is_fatal(code):
    marked = []
    bot = FakeTelegram({"getMe": telegram.TelegramError("getMe: Unauthorized", code)}, ready=lambda: marked.append(1))
    with pytest.raises(telegram.AuthFailed):
        asyncio.run(bot.run())
    assert marked == []


def test_a_token_revoked_while_polling_is_fatal():
    bot = FakeTelegram({"getMe": {"username": "x"},
                        "getUpdates": telegram.TelegramError("getUpdates: Unauthorized", 401)})
    with pytest.raises(telegram.AuthFailed):
        asyncio.run(bot.run())


def test_other_telegram_errors_are_not_fatal(monkeypatch):
    """A 502 while polling is Telegram having a moment: wait and poll again."""
    bot = FakeTelegram({"getMe": {"username": "x"}, "getUpdates": telegram.TelegramError("Bad Gateway", 502)})

    async def no_wait(_):
        raise asyncio.CancelledError  # stop after the first retry instead of sleeping

    monkeypatch.setattr(telegram.asyncio, "sleep", no_wait)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(bot.run())
    assert bot.calls == ["getMe", "setMyCommands", "getUpdates"]


@pytest.mark.parametrize("error", [discord.LoginFailure("Improper token has been passed."),
                                   telegram.AuthFailed("telegram: the token was refused")])
def test_supervised_does_not_retry_a_refused_token(monkeypatch, error):
    monkeypatch.setattr(entry, "RESTART_AFTER", 0.01)
    runs = []

    async def start():
        runs.append(1)
        raise error

    with pytest.raises(type(error)):
        asyncio.run(entry.supervised("discord", start))
    assert runs == [1]


def test_a_refused_token_ends_the_process_with_an_error(monkeypatch, tmp_path):
    """Both bots configured, Telegram's token is refused: the process exits non-zero, never ready."""
    monkeypatch.setenv("DISCORD_TOKEN", "x")
    monkeypatch.setenv("TELEGRAM_TOKEN", "123:abc")
    monkeypatch.setenv("PROXYBOT_READY_FILE", str(tmp_path / "ready"))

    async def refused(self, method, **params):
        raise telegram.TelegramError(f"{method}: Unauthorized", 401)

    async def never(*args, **kwargs):
        await asyncio.sleep(3600)

    class Discord:  # logs in but never gets anywhere – the Telegram failure must end the process anyway
        def __init__(self, settings, ready=None):
            pass

        async def start(self, token):
            await asyncio.sleep(3600)

    monkeypatch.setattr(telegram.TelegramBot, "call", refused)
    monkeypatch.setattr(entry, "fetch_snapshot", never)
    monkeypatch.setattr(entry, "ProxyBot", Discord)
    with pytest.raises(SystemExit) as exit_info:
        entry.main()
    assert exit_info.value.code == 2
    assert not (tmp_path / "ready").exists()


def test_discord_marks_ready_on_login(tmp_path):
    from proxybot.bot import ProxyBot

    marked = []

    async def go():
        bot = ProxyBot(Settings(token="x", state_file=tmp_path / "state.json"), ready=lambda: marked.append(1))
        bot._layout_done = asyncio.Event()
        await bot.on_ready()  # no servers yet: nothing to set up

    asyncio.run(go())
    assert marked == [1]
