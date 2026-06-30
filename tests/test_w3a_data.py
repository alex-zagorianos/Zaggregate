"""Wave 3a - Adzuna dedup, extras merge/restore, concurrency-safe migration."""
import json
import sqlite3
import pytest

import models
import tracker.db as db
from tracker import service
from models import JobResult


def test_adzuna_se_token_dedups():
    a = ("https://www.adzuna.com/land/ad/5776175260?se=AAA&utm_medium=api"
         "&v=ABC")
    b = ("https://www.adzuna.com/land/ad/5776175260?se=BBB&utm_medium=api"
         "&v=ABC")
    assert models.normalize_url(a) == models.normalize_url(b)


def test_safe_add_column_idempotent():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE t (a TEXT)")
    db._safe_add_column(conn, "t", "b", "TEXT DEFAULT ''")
    db._safe_add_column(conn, "t", "b", "TEXT DEFAULT ''")  # must not raise
    cols = {r[1] for r in conn.execute("PRAGMA table_info(t)")}
    assert "b" in cols


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "tracker.db")
    db.init_db()
    return db.DB_PATH


def test_apply_rerank_merges_extras(tmp_db):
    db.inbox_add_many([JobResult(
        title="Controls Engineer", company="Acme", location="Cincinnati, OH",
        salary_min=None, salary_max=None, description="plc", url="https://x.co/1",
        source_keyword="", created="2026-06-30", source_api="adzuna", score=70)])
    row = db.inbox_all()[0]
    db.inbox_merge_extras(int(row["id"]), {"browse": {"mode": "Remote"}})
    service.apply_rerank_scores([{"id": int(row["id"]), "new_fit": 80,
                                  "extras": json.dumps({"rank": 1})}])
    extras = json.loads(db.inbox_all()[0]["extras"])
    assert extras.get("rank") == 1 and extras.get("browse") == {"mode": "Remote"}


def test_restore_dismissed_keeps_extras(tmp_db):
    n = service.restore_dismissed_rows([{
        "norm_url": "x.co/9", "url": "https://x.co/9", "title": "T", "company": "C",
        "date_added": "2026-06-30", "extras": json.dumps({"rank": 3})}])
    assert n == 1
    extras = json.loads(db.inbox_all()[0]["extras"])
    assert extras.get("rank") == 3
