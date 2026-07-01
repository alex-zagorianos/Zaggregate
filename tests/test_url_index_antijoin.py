"""Index on applications.url/norm_url + SQL anti-join (NOT EXISTS) for
tracked/dismissed filtering — avoids materializing the full URL sets in
Python as the applications/dismissed tables grow (2026-07-01 storage
research, item 3). tracked_urls()/dismissed_urls()/seen_urls() keep their
existing signature and return type (a Python set) for existing callers."""
import sqlite3

import pytest

import tracker.db as db
from models import JobResult


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "tracker.db")
    return db.DB_PATH


def _job(url, company="Acme", title="Eng", score=50, created=""):
    return JobResult(title=title, company=company, location="", salary_min=None,
                     salary_max=None, description="", url=url, source_keyword="",
                     created=created, source_api="greenhouse", score=score)


def test_applications_url_and_norm_url_indexes_exist(tmp_db):
    db.init_db()
    with db.get_conn() as conn:
        names = {r["name"] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'")}
    assert "idx_applications_url" in names
    assert "idx_applications_norm_url" in names


def test_inbox_url_index_exists(tmp_db):
    db.init_db()
    with db.get_conn() as conn:
        names = {r["name"] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'")}
    assert "idx_inbox_url" in names


def test_add_job_populates_norm_url(tmp_db):
    db.init_db()
    raw = "https://Jobs.Example.com/1/?utm_source=x"
    jid = db.add_job("Eng", "Acme", url=raw)
    with db.get_conn() as conn:
        row = conn.execute("SELECT norm_url FROM applications WHERE id=?",
                           (jid,)).fetchone()
    assert row["norm_url"] == db.normalize_url(raw)


def test_add_job_without_url_leaves_norm_url_blank(tmp_db):
    db.init_db()
    jid = db.add_job("Eng", "Acme")
    with db.get_conn() as conn:
        row = conn.execute("SELECT norm_url FROM applications WHERE id=?",
                           (jid,)).fetchone()
    assert row["norm_url"] == ""


def test_migration_backfills_norm_url_for_preexisting_rows(tmp_path, monkeypatch):
    """A pre-migration applications row (created before norm_url existed) must
    get its norm_url backfilled once init_db() runs the migration."""
    db_path = tmp_path / "tracker.db"
    monkeypatch.setattr(db, "DB_PATH", db_path)
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL, company TEXT NOT NULL, location TEXT DEFAULT '',
            url TEXT DEFAULT '', salary_text TEXT DEFAULT '', source TEXT DEFAULT 'manual',
            status TEXT DEFAULT 'interested', date_added TEXT NOT NULL,
            date_applied TEXT DEFAULT '', notes TEXT DEFAULT ''
        )
    """)
    conn.execute(
        "INSERT INTO applications (title, company, url, date_added) VALUES (?,?,?,?)",
        ("Legacy", "OldCo", "https://x.com/legacy?utm_source=old", "2026-01-01"),
    )
    conn.commit()
    conn.close()

    db.init_db()
    with db.get_conn() as c:
        row = c.execute(
            "SELECT norm_url FROM applications WHERE title='Legacy'").fetchone()
    assert row["norm_url"] == db.normalize_url("https://x.com/legacy?utm_source=old")


def test_update_job_url_refreshes_norm_url(tmp_db):
    """Editing an application's URL (the GUI's tracker-edit dialog does this)
    must keep norm_url in sync, or the anti-join would silently go stale."""
    db.init_db()
    jid = db.add_job("Eng", "Acme", url="https://x.com/old")
    new_url = "https://x.com/new?utm_source=mail"
    db.update_job(jid, url=new_url)
    with db.get_conn() as conn:
        row = conn.execute("SELECT norm_url FROM applications WHERE id=?",
                           (jid,)).fetchone()
    assert row["norm_url"] == db.normalize_url(new_url)
    # the OLD url must no longer show up as tracked
    assert db.normalize_url("https://x.com/old") not in db.tracked_urls()
    assert db.normalize_url(new_url) in db.tracked_urls()


def test_urls_not_seen_excludes_tracked_and_dismissed(tmp_db):
    db.init_db()
    db.add_job("Eng", "Acme", url="https://x.com/tracked")
    db.dismiss_url("https://x.com/dismissed")
    candidates = [
        db.normalize_url("https://x.com/tracked"),
        db.normalize_url("https://x.com/dismissed"),
        db.normalize_url("https://x.com/fresh"),
    ]
    unseen = db.urls_not_seen(candidates)
    assert unseen == {db.normalize_url("https://x.com/fresh")}


def test_urls_not_seen_matches_seen_urls_semantics(tmp_db):
    """urls_not_seen(candidates) must be equivalent to
    {u for u in candidates if u not in seen_urls()} for any candidate batch —
    same result, different (indexed, batch-bounded) SQL path."""
    db.init_db()
    db.add_job("Eng", "Acme", url="https://x.com/a")
    db.dismiss_url("https://x.com/b")
    candidates = [db.normalize_url(u) for u in
                  ["https://x.com/a", "https://x.com/b", "https://x.com/c"]] + [""]
    seen = db.seen_urls()
    expected = {u for u in candidates if u and u not in seen}
    assert db.urls_not_seen(candidates) == expected


def test_urls_not_seen_empty_input(tmp_db):
    db.init_db()
    assert db.urls_not_seen([]) == set()
    assert db.urls_not_seen(["", None]) == set()


def test_inbox_add_many_still_skips_tracked_and_dismissed(tmp_db):
    """Behavior parity: inbox_add_many's internal seen-check now uses the
    anti-join helper, but must still produce identical skip behavior."""
    db.init_db()
    db.add_job("Eng", "Acme", url="https://x.com/tracked")
    db.dismiss_url("https://x.com/dismissed")
    added = db.inbox_add_many([
        _job("https://x.com/tracked"),
        _job("https://x.com/dismissed"),
        _job("https://x.com/fresh"),
    ])
    assert added == 1
    urls = {r["url"] for r in db.inbox_all()}
    assert urls == {"https://x.com/fresh"}


def test_tracked_urls_dismissed_urls_seen_urls_signatures_unchanged(tmp_db):
    """The three existing public functions keep returning plain Python sets —
    no signature/return-type change for existing callers."""
    db.init_db()
    db.add_job("Eng", "Acme", url="https://x.com/a")
    db.dismiss_url("https://x.com/b")
    assert isinstance(db.tracked_urls(), set)
    assert isinstance(db.dismissed_urls(), set)
    assert isinstance(db.seen_urls(), set)
    assert db.seen_urls() == db.tracked_urls() | db.dismissed_urls()
