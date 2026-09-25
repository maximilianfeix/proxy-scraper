"""-o - prints the hits to stdout, the interface moves to stderr (#105)."""

import io

from proxyscraper import cli
from proxyscraper.checker import CheckResult
from proxyscraper.output import ResultWriter
from proxyscraper.ui import widgets

ROWS = [CheckResult("http 1.1.1.1:80", "http", "1.1.1.1:80", 300, "9.9.9.9"),
        CheckResult("socks5 2.2.2.2:1080", "socks5", "2.2.2.2:1080", 100, "9.9.9.9")]


def test_hits_go_to_the_stream_fastest_first(tmp_path):
    out = io.StringIO()
    files = ResultWriter(run_dir=tmp_path, stdout=out).finalize(ROWS)
    assert out.getvalue() == "socks5://2.2.2.2:1080\nhttp://1.1.1.1:80\n"
    assert not any("-o" in label for label in files)  # no "-" file anywhere
    assert not (tmp_path / "-").exists()


def test_a_closed_pipe_is_fine(tmp_path):
    class Closed(io.StringIO):
        def write(self, _):
            raise BrokenPipeError

    ResultWriter(run_dir=tmp_path, stdout=Closed()).finalize(ROWS)  # `| head` stopped reading – no traceback


def test_the_interface_moves_to_stderr(monkeypatch):
    seen = {}

    class FakeRun:
        def __init__(self, opts, show_banner=True):
            seen["output"] = opts.output
            seen["stderr"] = widgets.console.stderr

        async def execute(self):
            return 0

    monkeypatch.setattr(cli, "Run", FakeRun)
    monkeypatch.setattr(widgets, "console", widgets.console)  # restored afterwards
    assert cli.run(["-y", "-o", "-"]) == 0
    assert seen == {"output": "-", "stderr": True}
