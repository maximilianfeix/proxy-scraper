"""--list-sources --json: the source ranking for scripts."""

import json
import time
from datetime import datetime, timezone

from proxyscraper import cli
from proxyscraper import sources as srcs


def test_ranking_as_json_on_stdout(tmp_path, monkeypatch, capsys):
    st = srcs.SourceStats(tmp_path / "s.json")
    now = time.time()
    st.record_fetch("https://good.example/http.txt", b"a", 100, now=now)
    st.record_checks({"https://good.example/http.txt": (200, 80)})
    st.record_fetch("https://bad.example/http.txt", b"b", 100, now=now)
    st.record_checks({"https://bad.example/http.txt": (200, 1)})
    monkeypatch.setattr(srcs, "SourceStats", lambda: st)
    monkeypatch.setattr(srcs, "load_source_file", lambda: ({"https://good.example/http.txt": "http"}, []))
    monkeypatch.setattr(srcs, "load_discovered", dict)
    assert cli.run(["--list-sources", "5", "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert [s["url"] for s in out] == ["https://good.example/http.txt", "https://bad.example/http.txt"]
    first = out[0]
    assert first["status"] == "active" and first["checked"] == 200 and first["working"] == 80
    assert 0 < first["hit_rate"] < 1
    assert first["last_change"].startswith(datetime.now(timezone.utc).strftime("%Y-%m-%d"))


def test_json_alone_is_an_error(capsys):
    try:
        cli.run(["--json"])
    except SystemExit as e:
        assert e.code == 2
    assert "--list-sources" in capsys.readouterr().err
