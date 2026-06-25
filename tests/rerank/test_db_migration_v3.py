import sqlite3
import pytest
from pathlib import Path

import tracker.db as db

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "rerank" / "v2_populated.sql"


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "tracker.db")
    return db.DB_PATH


@pytest.fixture
def v2_db(tmp_db):
    conn = sqlite3.connect(str(tmp_db))
    conn.executescript(FIXTURE.read_text(encoding="utf-8"))
    conn.commit()
    conn.close()
    return tmp_db


def test_schema_version_is_current():
    assert db.SCHEMA_VERSION == 4


def test_v2_to_v3_migrates_and_preserves_rows(v2_db):
    assert db.init_db() is True               # migration ran
    with db.get_conn() as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 4
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(inbox)")}
        assert "extras" in cols
        tables = {r["name"] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        assert "score_history" in tables
        row = conn.execute("SELECT title FROM inbox WHERE id=1").fetchone()
        assert row["title"] == "Software Developer"      # data survived


def test_migration_backs_up_db(v2_db, tmp_path):
    db.init_db()
    backups = list(tmp_path.glob("tracker.db.bak-v*"))
    assert backups, "expected a pre-migration backup"


def test_init_db_idempotent_at_v3(tmp_db):
    assert db.init_db() is True
    assert db.init_db() is False              # fast path at v3


def test_inbox_set_fit_writes_history_before_update(tmp_db):
    db.init_db()
    iid = db.inbox_add_many([_inbox_job()])  # see helper below
    rows = db.inbox_all()
    inbox_id = rows[0]["id"]
    db.inbox_set_fit(inbox_id, 88, "great", source="file_import")
    with db.get_conn() as conn:
        h = conn.execute(
            "SELECT old_fit, new_fit, source FROM score_history WHERE inbox_id=?",
            (inbox_id,)).fetchone()
        cur = conn.execute("SELECT fit FROM inbox WHERE id=?", (inbox_id,)).fetchone()
    assert h["old_fit"] == -1 and h["new_fit"] == 88 and h["source"] == "file_import"
    assert cur["fit"] == 88


def test_undo_last_rerank_reverts(tmp_db):
    db.init_db()
    db.inbox_add_many([_inbox_job()])
    inbox_id = db.inbox_all()[0]["id"]
    db.inbox_set_fit(inbox_id, 88, "great", source="file_import")
    restored = db.inbox_undo_last_rerank("file_import")
    assert restored == 1
    with db.get_conn() as conn:
        assert conn.execute("SELECT fit FROM inbox WHERE id=?",
                            (inbox_id,)).fetchone()["fit"] == -1


def _inbox_job():
    from models import JobResult
    return JobResult(title="Controls Engineer", company="Beta",
                     location="Cincinnati, OH", salary_min=None, salary_max=None,
                     description="plc", url="https://x.co/9", source_keyword="",
                     created="2026-06-21", source_api="adzuna", score=60)
