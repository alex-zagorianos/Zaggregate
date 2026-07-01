"""FTS5 full-text search over inbox(title, company, location, description) —
external-content vtable + sync triggers + LIKE fallback for FTS5-less builds
(2026-07-01 storage research, item 2)."""
import sqlite3

import pytest

import tracker.db as db
from models import JobResult


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "tracker.db")
    return db.DB_PATH


def _job(url, title="Controls Engineer", company="Acme", location="Cincinnati, OH",
         description="", score=50, created=""):
    return JobResult(title=title, company=company, location=location,
                     salary_min=None, salary_max=None, description=description,
                     url=url, source_keyword="", created=created,
                     source_api="greenhouse", score=score)


def test_inbox_fts_table_and_triggers_created(tmp_db):
    db.init_db()
    with db.get_conn() as conn:
        names = {r["name"] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table','trigger')")}
    assert "inbox_fts" in names
    assert {"inbox_fts_ai", "inbox_fts_ad", "inbox_fts_au"} <= names


def test_inbox_search_finds_by_title_company_description(tmp_db):
    db.init_db()
    db.inbox_add_many([
        _job("https://x.com/1", title="Controls Engineer", company="Acme",
             description="PLC programming, Epic systems integration"),
        _job("https://x.com/2", title="Nurse", company="Globex",
             description="Bedside care"),
    ])
    hits = db.inbox_search("Epic")
    assert len(hits) == 1
    assert hits[0]["title"] == "Controls Engineer"

    hits2 = db.inbox_search("nurse")
    assert len(hits2) == 1
    assert hits2[0]["company"] == "Globex"


def test_inbox_search_returns_full_rows(tmp_db):
    db.init_db()
    db.inbox_add_many([_job("https://x.com/1", title="Marker Term",
                            description="d")])
    hits = db.inbox_search("Marker")
    assert len(hits) == 1
    row = hits[0]
    # full inbox row, not just the FTS-indexed columns
    for col in ("id", "url", "score", "fit", "created", "date_added"):
        assert col in row


def test_inbox_search_empty_query_returns_empty(tmp_db):
    db.init_db()
    assert db.inbox_search("") == []
    assert db.inbox_search("   ") == []


def test_inbox_search_no_matches_returns_empty(tmp_db):
    db.init_db()
    db.inbox_add_many([_job("https://x.com/1")])
    assert db.inbox_search("zzz_no_such_term_anywhere") == []


def test_inbox_search_stays_in_sync_after_delete(tmp_db):
    db.init_db()
    db.inbox_add_many([_job("https://x.com/1", title="Unique Term Xyzzy")])
    assert len(db.inbox_search("Xyzzy")) == 1
    row = db.inbox_all()[0]
    db.inbox_delete(row["id"])
    assert db.inbox_search("Xyzzy") == []


def test_inbox_search_stays_in_sync_after_raw_update(tmp_db):
    """Any UPDATE on inbox (not just the db.py helper functions) must keep the
    FTS index in sync via the AFTER UPDATE trigger."""
    db.init_db()
    db.inbox_add_many([_job("https://x.com/1", title="Old Title Marker")])
    row = db.inbox_all()[0]
    with db.get_conn() as conn:
        conn.execute("UPDATE inbox SET title=? WHERE id=?",
                     ("New Title Marker", row["id"]))
        conn.commit()
    assert db.inbox_search("Old") == []
    hits = db.inbox_search("New")
    assert len(hits) == 1


def test_inbox_search_backfills_preexisting_rows_on_migration(tmp_path, monkeypatch):
    """A DB that already had inbox rows before the FTS5 table existed (e.g. an
    upgrade from an older SCHEMA_VERSION) must be searchable immediately after
    init_db() runs the migration — not just for rows added afterward."""
    db_path = tmp_path / "tracker.db"
    monkeypatch.setattr(db, "DB_PATH", db_path)
    db.init_db()
    db.inbox_add_many([_job("https://x.com/1", title="Preexisting Marker Term")])
    # Simulate an older schema, as if this row existed before the FTS5
    # migration landed: drop the FTS objects and rewind user_version.
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute("DROP TABLE IF EXISTS inbox_fts")
        for trig in ("inbox_fts_ai", "inbox_fts_ad", "inbox_fts_au"):
            conn.execute(f"DROP TRIGGER IF EXISTS {trig}")
        conn.execute(f"PRAGMA user_version = {db.SCHEMA_VERSION - 1}")
        conn.commit()
    assert db.init_db() is True  # re-migrates -> current
    hits = db.inbox_search("Preexisting")
    assert len(hits) == 1


class _FTS5LessConnection:
    """Wraps a real sqlite3.Connection, faking 'no such module: fts5' for any
    CREATE VIRTUAL TABLE ... USING fts5 statement — sqlite3.Connection is a
    C-extension type (its methods can't be monkeypatched directly), so this
    proxy stands in for a genuinely FTS5-less SQLite build."""

    def __init__(self, real):
        object.__setattr__(self, "_real", real)

    def execute(self, sql, *args, **kwargs):
        if "USING fts5" in sql:
            raise sqlite3.OperationalError("no such module: fts5")
        return self._real.execute(sql, *args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._real, name)

    def __setattr__(self, name, value):
        setattr(self._real, name, value)

    def __enter__(self):
        self._real.__enter__()
        return self

    def __exit__(self, exc_type, exc, tb):
        return self._real.__exit__(exc_type, exc, tb)


def test_inbox_search_falls_back_to_like_without_fts5(tmp_path, monkeypatch):
    """Simulate an FTS5-less SQLite build: the CREATE VIRTUAL TABLE call fails
    during init_db() (as it would with 'no such module: fts5'), so inbox_fts
    and its triggers never get created — inbox writes and inbox_search must
    both keep working (via the LIKE substring fallback) instead of crashing."""
    db_path = tmp_path / "tracker.db"
    monkeypatch.setattr(db, "DB_PATH", db_path)

    real_connect = sqlite3.connect

    def fake_connect(*args, **kwargs):
        return _FTS5LessConnection(real_connect(*args, **kwargs))

    with monkeypatch.context() as m:
        m.setattr(db.sqlite3, "connect", fake_connect)
        db.init_db()

    with sqlite3.connect(str(db_path)) as conn:
        names = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table','trigger')")}
    assert "inbox_fts" not in names
    assert "inbox_fts_ai" not in names

    db.inbox_add_many([_job("https://x.com/1", title="Fallback Marker Term")])
    hits = db.inbox_search("Fallback")
    assert len(hits) == 1
    assert hits[0]["title"] == "Fallback Marker Term"


def test_inbox_search_handles_special_characters_safely(tmp_db):
    """FTS5 query-syntax characters (quotes, hyphens, colons, asterisks) in raw
    user input must never raise a MATCH syntax error."""
    db.init_db()
    db.inbox_add_many([_job("https://x.com/1", title="C++ / .NET Engineer")])
    for q in ['"unterminated', "C++ -senior", "foo* OR bar", "a:b", "weird'quote"]:
        db.inbox_search(q)  # must not raise


def test_fts_optimize_invoked_after_bulk_add(tmp_db, monkeypatch):
    db.init_db()
    calls = []
    orig = db._fts_optimize
    monkeypatch.setattr(db, "_fts_optimize", lambda conn: (calls.append(1), orig(conn)))
    db.inbox_add_many([_job("https://x.com/1")])
    assert calls == [1]


def test_fts_optimize_skipped_when_nothing_added(tmp_db, monkeypatch):
    db.init_db()
    calls = []
    monkeypatch.setattr(db, "_fts_optimize", lambda conn: calls.append(1))
    db.inbox_add_many([])
    assert calls == []


def test_fts_optimize_invoked_after_bulk_prune(tmp_db, monkeypatch):
    db.init_db()
    db.inbox_add_many([_job("https://x.com/1")])
    calls = []
    orig = db._fts_optimize
    monkeypatch.setattr(db, "_fts_optimize", lambda conn: (calls.append(1), orig(conn)))
    n = db.inbox_delete_urls(["https://x.com/1"])
    assert n == 1
    assert calls == [1]


def test_inbox_add_many_behavior_unchanged_by_fts_wiring(tmp_db):
    """Sanity: the FTS sync triggers/optimize call must not change
    inbox_add_many's dedup/count/cap behavior for existing callers."""
    db.init_db()
    # Distinct titles -> distinct job_keys so the ONLY collapse here is the
    # duplicate norm_url (C1 job_key coalescing is exercised separately).
    added = db.inbox_add_many([
        _job("https://x.com/1", company="Acme", title="Eng One"),
        _job("https://x.com/1", company="Acme", title="Eng One"),  # dup norm_url -> ignored
        _job("https://x.com/2", company="Acme", title="Eng Two"),
    ])
    assert added == 2
    assert db.inbox_count() == 2
