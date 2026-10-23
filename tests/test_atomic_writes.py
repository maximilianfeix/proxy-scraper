"""State files written by several writers at once (threads here; CLI and MCP processes share the data folder too).

Every writer gets its own temporary file next to the target: overlapping writes never collide, the target
is always one complete version, and nothing is left behind – also when a write fails half-way."""

import json
import os
import threading

import pytest

from proxyscraper import paths
from proxyscraper.asndb import AsnDB
from proxyscraper.fetchcache import FetchCache
from proxyscraper.geodb import CountryDB

WRITERS = 4


@pytest.fixture
def replace_together(monkeypatch):
    """Every writer has finished its temporary file before the first one renames it – the worst overlap,
    without relying on timing."""
    barrier = threading.Barrier(WRITERS, timeout=10)
    real_replace = os.replace
    waited = threading.local()

    def replace(src, dst, *args, **kwargs):
        # only a thread's first rename waits: on Windows overlapping renames onto one target fail with
        # PermissionError and are retried (paths._replace), and a retry must not wait for writers that are done
        if not getattr(waited, "done", False):
            waited.done = True
            barrier.wait()
        return real_replace(src, dst, *args, **kwargs)

    monkeypatch.setattr(os, "replace", replace)  # pathlib's Path.replace goes through os.replace too


def run_parallel(target):
    errors = []

    def wrapped(i):
        try:
            target(i)
        except BaseException as e:  # noqa: BLE001 – collected and asserted below
            errors.append(e)

    threads = [threading.Thread(target=wrapped, args=(i,)) for i in range(WRITERS)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(20)
    return errors


def payload(i):
    return json.dumps({"writer": i, "rows": [i] * 5000})


def test_overlapping_atomic_writes(tmp_path, replace_together):
    target = tmp_path / "history.json"
    errors = run_parallel(lambda i: paths.atomic_write(target, payload(i)))
    assert errors == []
    data = json.loads(target.read_text(encoding="utf-8"))  # complete and valid: exactly one writer's version
    assert data["rows"] == [data["writer"]] * 5000
    assert sorted(p.name for p in tmp_path.iterdir()) == ["history.json"]  # no temporary files left


def test_overlapping_fetch_cache_stores(tmp_path, replace_together):
    url = "http://list.example/proxies.txt"

    def store(i):
        cache = FetchCache(tmp_path)
        cache.store(url, {b"etag": f'"v{i}"'.encode()}, f"http 1.1.1.{i}:80\n", "http")

    assert run_parallel(store) == []
    files = sorted(p.name for p in tmp_path.iterdir())
    assert len(files) == 1 and files[0].endswith(".txt.gz")
    cache = FetchCache(tmp_path)
    cache.entries[url] = {"file": files[0]}
    assert cache.load(url) in {f"http 1.1.1.{i}:80\n" for i in range(WRITERS)}


@pytest.mark.parametrize("db_class, csv", [
    (CountryDB, "\n".join(f"10.0.{i}.0,10.0.{i}.255,DE" for i in range(50))),
    (AsnDB, "\n".join(f'10.0.{i}.0,10.0.{i}.255,{i},"Org {i}"' for i in range(50))),
])
def test_overlapping_database_saves(tmp_path, replace_together, db_class, csv):
    target = tmp_path / "db.bin"
    errors = run_parallel(lambda i: db_class.from_csv(csv, f"2026-0{i + 1}").save(target))
    assert errors == []
    db = db_class.load(target)
    assert db is not None and db.month in {f"2026-0{i + 1}" for i in range(WRITERS)}
    assert sorted(p.name for p in tmp_path.iterdir()) == ["db.bin"]


def test_failed_write_keeps_the_old_file_and_leaves_nothing_behind(tmp_path):
    target = tmp_path / "prefs.json"
    paths.atomic_write(target, '{"old": true}')
    with pytest.raises(UnicodeEncodeError):
        paths.atomic_write(target, "\ud800 cannot be encoded")
    assert target.read_text(encoding="utf-8") == '{"old": true}'
    assert sorted(p.name for p in tmp_path.iterdir()) == ["prefs.json"]


def test_failed_rename_leaves_nothing_behind(tmp_path, monkeypatch):
    target = tmp_path / "prefs.json"

    def broken(src, dst):
        raise PermissionError("target is locked")

    monkeypatch.setattr(os, "replace", broken)
    with pytest.raises(PermissionError):
        paths.atomic_write(target, "{}")
    assert list(tmp_path.iterdir()) == []


@pytest.mark.skipif(os.name == "nt", reason="POSIX permissions")
@pytest.mark.parametrize("umask", [0o022, 0o077])
def test_written_files_follow_the_current_umask(tmp_path, umask):
    # the mask in effect at write time, not the one at import time – a caller that tightens it gets private files
    target = tmp_path / "summary.json"
    old = os.umask(umask)
    try:
        paths.atomic_write(target, "{}")
    finally:
        os.umask(old)
    assert target.stat().st_mode & 0o777 == 0o666 & ~umask
