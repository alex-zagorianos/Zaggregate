"""get_conn must enable WAL + busy_timeout (2026-06 review)."""
import tracker.db as db


def test_get_conn_sets_wal_and_busy_timeout(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "t.db"))
    conn = db.get_conn()
    try:
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 30000
        assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    finally:
        conn.close()
