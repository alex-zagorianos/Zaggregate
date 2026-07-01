"""get_conn must enable WAL + busy_timeout (2026-06 review), plus the
completed WAL pragma set + checkpoint-on-exit (2026-07-01 storage research)."""
import atexit

import pytest

import tracker.db as db


def test_get_conn_sets_wal_and_busy_timeout(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "t.db"))
    conn = db.get_conn()
    try:
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 30000
        assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    finally:
        conn.close()


def test_get_conn_sets_synchronous_normal(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "t.db"))
    conn = db.get_conn()
    try:
        # 0=OFF, 1=NORMAL, 2=FULL, 3=EXTRA
        assert conn.execute("PRAGMA synchronous").fetchone()[0] == 1
    finally:
        conn.close()


def test_get_conn_sets_temp_store_memory(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "t.db"))
    conn = db.get_conn()
    try:
        assert conn.execute("PRAGMA temp_store").fetchone()[0] == 2  # 2=MEMORY
    finally:
        conn.close()


def test_get_conn_sets_bounded_mmap_size(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "t.db"))
    conn = db.get_conn()
    try:
        mmap = conn.execute("PRAGMA mmap_size").fetchone()[0]
        assert 0 < mmap <= 256 * 1024 * 1024
    finally:
        conn.close()


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "t.db"))
    return db.DB_PATH


def test_checkpoint_truncates_wal_sidecar(tmp_db, tmp_path):
    db.init_db()
    db.add_job("Eng", "Acme")
    wal_path = tmp_path / "t.db-wal"
    assert wal_path.exists()
    db.checkpoint()
    # TRUNCATE-mode checkpoint shrinks the -wal sidecar to 0 bytes.
    assert wal_path.stat().st_size == 0


def test_close_db_is_a_checkpoint_alias(tmp_db, tmp_path):
    db.init_db()
    db.add_job("Eng", "Acme")
    db.close_db()
    assert (tmp_path / "t.db-wal").stat().st_size == 0


def test_checkpoint_never_raises_when_db_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "does_not_exist.db"))
    db.checkpoint()  # must not raise, must not create the file
    assert not (tmp_path / "does_not_exist.db").exists()


def test_checkpoint_never_raises_when_db_path_unresolvable(tmp_path, monkeypatch):
    """Guard: checkpoint() must swallow any error, not just a missing file."""
    def boom():
        raise RuntimeError("boom")
    monkeypatch.setattr(db, "current_db_path", boom)
    db.checkpoint()  # must not raise


def test_checkpoint_registered_for_atexit(monkeypatch):
    """Verify the module wires checkpoint() into atexit.register at import
    time. CPython 3.12's atexit is a C-accelerated module with no introspect-
    able handler list (no `_exithandlers`), so this spies on atexit.register
    and reloads the module rather than inspecting private state."""
    import importlib

    calls = []
    monkeypatch.setattr(atexit, "register", lambda fn: calls.append(fn))
    importlib.reload(db)
    try:
        assert any(fn is db.checkpoint for fn in calls)
    finally:
        # Restore real atexit wiring for the (already-imported) module before
        # the monkeypatch reverts, so the process ends up in a normal state.
        monkeypatch.undo()
        importlib.reload(db)
