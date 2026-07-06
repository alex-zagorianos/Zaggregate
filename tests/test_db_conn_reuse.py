"""S38 connection-reuse tests for tracker/db.get_conn().

The contract under test:
* same thread + same db path + idle connection  -> the SAME cached object;
* a nested call while the cached connection is mid-transaction -> a FRESH
  object (pre-S38 semantics: an inner `with` can never commit the outer);
* different threads -> different connections;
* a db-path switch (project switch / test override) retires the cached one;
* a caller closing the handout self-heals on the next call;
* close_all_connections()/release_for_restore() drop the Windows file locks
  deterministically (the S36 restore bug must stay dead).
"""
import os
import sqlite3
import threading

import pytest

from tracker import db


@pytest.fixture()
def tmp_db(tmp_path, monkeypatch):
    """Point tracker.db at a fresh temp file and start with a clean cache."""
    db.close_all_connections()
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    yield tmp_path / "t.db"
    db.close_all_connections()


def test_same_thread_reuses_connection(tmp_db):
    c1 = db.get_conn()
    c2 = db.get_conn()
    assert c1 is c2


def test_nested_call_in_transaction_gets_fresh_connection(tmp_db):
    outer = db.get_conn()
    with outer:  # opens a transaction on first write
        outer.execute(
            "INSERT INTO applications (title, company, date_added) "
            "VALUES ('t', 'c', '2026-07-05')")
        assert outer.in_transaction
        inner = db.get_conn()
        assert inner is not outer
        # WAL snapshot isolation: the inner (read) connection sees the
        # pre-transaction state, and its `with` exit must not commit/end the
        # OUTER transaction. (Nested WRITES block on the single WAL writer —
        # that was equally true pre-S38 and is not a supported pattern.)
        with inner:
            n = inner.execute("SELECT COUNT(*) FROM applications").fetchone()[0]
        assert n == 0
        assert outer.in_transaction
        inner.close()
    # After the outer commit the cached connection is idle and reused again.
    assert db.get_conn() is outer


def test_threads_get_distinct_connections(tmp_db):
    main_conn = db.get_conn()
    seen = {}

    def worker():
        seen["conn"] = db.get_conn()

    t = threading.Thread(target=worker)
    t.start()
    t.join()
    assert seen["conn"] is not main_conn


def test_db_path_switch_retires_cached_connection(tmp_db, tmp_path, monkeypatch):
    c1 = db.get_conn()
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "other.db")
    db.init_db()
    c2 = db.get_conn()
    assert c2 is not c1
    # The old handle was closed, not leaked.
    with pytest.raises(sqlite3.ProgrammingError):
        c1.execute("SELECT 1")


def test_caller_close_self_heals(tmp_db):
    c1 = db.get_conn()
    c1.close()  # analytics/inbox_health-style call sites do this
    c2 = db.get_conn()
    assert c2 is not c1
    assert c2.execute("SELECT 1").fetchone()[0] == 1


def test_close_all_connections_drops_cache(tmp_db):
    c1 = db.get_conn()
    db.close_all_connections()
    with pytest.raises(sqlite3.ProgrammingError):
        c1.execute("SELECT 1")
    c2 = db.get_conn()          # reopens cleanly afterwards
    assert c2.execute("SELECT 1").fetchone()[0] == 1


def test_release_for_restore_unlocks_file_for_overwrite(tmp_db, tmp_path):
    # Simulate the backup-restore flow: use the db, then release, then the
    # file must be replaceable on Windows (no [WinError 32] open-handle lock).
    conn = db.get_conn()
    conn.execute("SELECT 1").fetchone()
    db.release_for_restore()

    replacement = tmp_path / "restored.db"
    src = sqlite3.connect(str(replacement))
    src.execute("CREATE TABLE marker (x)")
    src.commit()
    src.close()
    os.replace(replacement, tmp_db)   # raises PermissionError if still locked

    fresh = db.get_conn()
    names = {r[0] for r in fresh.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert "marker" in names


def test_close_db_is_repeat_safe(tmp_db):
    db.get_conn()
    db.close_db()
    db.close_db()
    assert db.get_conn().execute("SELECT 1").fetchone()[0] == 1
