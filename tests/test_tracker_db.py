import sqlite3

import pytest

import tracker.db as db


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "tracker.db")
    return db.DB_PATH


def test_init_creates_schema_and_crud(tmp_db):
    db.init_db()
    jid = db.add_job("Controls Engineer", "Acme", location="Cincinnati, OH",
                     url="https://x.com/1", follow_up_date="2026-06-10",
                     contact="Jane Recruiter")
    job = db.get_job(jid)
    assert job["title"] == "Controls Engineer"
    assert job["follow_up_date"] == "2026-06-10"
    assert job["contact"] == "Jane Recruiter"

    db.update_job(jid, status="applied", resume_path="C:/out/resume.docx")
    assert db.get_job(jid)["status"] == "applied"
    assert db.get_job(jid)["resume_path"].endswith("resume.docx")

    counts = db.get_counts()
    assert counts["all"] == 1 and counts["applied"] == 1


def test_migration_adds_columns_to_old_schema(tmp_db):
    """An existing DB on the original 11-column schema must upgrade in place."""
    conn = sqlite3.connect(str(tmp_db))
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
        "INSERT INTO applications (title, company, date_added) VALUES (?,?,?)",
        ("Legacy Job", "OldCo", "2026-05-01"),
    )
    conn.commit()
    conn.close()

    db.init_db()  # should ALTER in the new columns without losing the row

    rows = db.get_all()
    assert len(rows) == 1 and rows[0]["title"] == "Legacy Job"
    for col in ("follow_up_date", "deadline", "contact", "description", "resume_path"):
        assert col in rows[0]


def test_migration_is_idempotent(tmp_db):
    db.init_db()
    db.init_db()  # second call must not raise (duplicate-column guard)
    db.add_job("T", "C")
    assert db.get_counts()["all"] == 1


# ── dedup helpers ─────────────────────────────────────────────────────────────

def test_normalize_url():
    assert db.normalize_url("https://Jobs.Example.com/view/1/?utm=x") == "jobs.example.com/view/1"
    assert db.normalize_url("https://jobs.example.com/view/1") == "jobs.example.com/view/1"
    assert db.normalize_url("") == ""


def test_seen_urls_includes_tracked_and_dismissed(tmp_db):
    db.init_db()
    db.add_job("Eng", "Acme", url="https://x.com/tracked/1?ref=a")
    db.dismiss_url("https://x.com/dismissed/2")
    seen = db.seen_urls()
    assert "x.com/tracked/1" in seen
    assert "x.com/dismissed/2" in seen
    assert db.normalize_url("https://x.com/tracked/1") in seen
