import sqlite3

import pytest

import tracker.db as db
from models import JobResult


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "tracker.db")
    return db.DB_PATH


def _job(url, company="Acme", title="Eng", score=50, created="", location=""):
    return JobResult(
        title=title, company=company, location=location, salary_min=None,
        salary_max=None, description="", url=url, source_keyword="",
        created=created, source_api="greenhouse", score=score,
    )


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
    # utm_* / fbclid / gclid / ref are tracking -> stripped (collapse to base).
    assert db.normalize_url("https://Jobs.Example.com/view/1/?utm_source=x") == "jobs.example.com/view/1"
    assert db.normalize_url("https://jobs.example.com/view/1") == "jobs.example.com/view/1"
    assert db.normalize_url("") == ""


def test_normalize_url_keeps_identity_params():
    """TRACK-4: identity params (gh_jid) must survive so distinct postings that
    differ only by their job id don't collapse; tracking-only diffs DO collapse."""
    a = db.normalize_url("https://boards.greenhouse.io/acme/jobs/123?gh_jid=123")
    b = db.normalize_url("https://boards.greenhouse.io/acme/jobs/123?gh_jid=456")
    assert a != b                      # different gh_jid -> distinct
    assert "gh_jid=123" in a

    # utm-only difference collapses to the same key.
    u1 = db.normalize_url("https://x.com/p?gh_jid=9&utm_source=mail")
    u2 = db.normalize_url("https://x.com/p?gh_jid=9&utm_campaign=spring")
    assert u1 == u2 == "x.com/p?gh_jid=9"


def test_init_db_gated_on_user_version(tmp_db):
    """TRACK-7: a second init_db on the same db takes the fast path and does no
    ALTER/probe work (returns the False sentinel)."""
    assert db.init_db() is True    # first call migrates
    assert db.init_db() is False   # already at SCHEMA_VERSION -> skip the scan


def test_idx_inbox_company_exists(tmp_db):
    """TRACK-10: the inbox(company) index must exist after init."""
    db.init_db()
    with db.get_conn() as conn:
        names = {r["name"] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'")}
    assert "idx_inbox_company" in names


def test_roundrobin_orders_by_created_within_run(tmp_db):
    """TRACK-8: same company, same date_added, same score -> intra-run order is
    decided by `created` (full timestamp) descending, not left undefined."""
    db.init_db()
    # Distinct titles -> distinct job_keys so these are two POSTINGS (not one
    # posting via two URLs, which C1 coalescing correctly merges).
    db.inbox_add_many([
        _job("https://x.com/old", company="Acme", title="Older Eng", score=50,
             created="2026-06-01T08:00:00"),
        _job("https://x.com/new", company="Acme", title="Newer Eng", score=50,
             created="2026-06-01T20:00:00"),
    ])
    rows = db.inbox_all(order="roundrobin")
    urls = [r["url"] for r in rows]
    # newer `created` first within the company partition
    assert urls.index("https://x.com/new") < urls.index("https://x.com/old")


def test_persisted_per_company_cap(tmp_db):
    """MISSED-4: the cap is enforced against the PERSISTED inbox across runs, so a
    board can't accrue cap rows every run."""
    db.init_db()
    # Distinct titles -> distinct job_keys so the cap (not C1 job_key coalescing)
    # is what limits how many land.
    # Run 1: 3 Acme jobs, cap 2 -> only 2 land.
    n1 = db.inbox_add_many(
        [_job(f"https://x.com/a{i}", company="Acme", title=f"Eng A{i}")
         for i in range(3)],
        per_company_cap=2)
    assert n1 == 2
    # Run 2: 3 more fresh Acme jobs, cap 2 -> already at 2, so 0 more land.
    n2 = db.inbox_add_many(
        [_job(f"https://x.com/b{i}", company="Acme", title=f"Eng B{i}")
         for i in range(3)],
        per_company_cap=2)
    assert n2 == 0
    assert db.inbox_company_counts()["acme"] == 2
    # A different company is unaffected.
    n3 = db.inbox_add_many(
        [_job("https://x.com/c0", company="Globex")], per_company_cap=2)
    assert n3 == 1


def test_seen_urls_includes_tracked_and_dismissed(tmp_db):
    db.init_db()
    db.add_job("Eng", "Acme", url="https://x.com/tracked/1?ref=a")
    db.dismiss_url("https://x.com/dismissed/2")
    seen = db.seen_urls()
    assert "x.com/tracked/1" in seen
    assert "x.com/dismissed/2" in seen
    assert db.normalize_url("https://x.com/tracked/1") in seen


def test_count_followups_due(tmp_db):
    db.init_db()
    # due: active status + follow_up_date in the past
    a = db.add_job("A", "Co", url="https://x/1", follow_up_date="2020-01-01")
    db.update_job(a, status="applied")
    # not due: follow_up_date in the future
    b = db.add_job("B", "Co", url="https://x/2", follow_up_date="2999-01-01")
    db.update_job(b, status="applied")
    # not counted: 'interested' is not an active-follow-up status (default)
    db.add_job("C", "Co", url="https://x/3", follow_up_date="2020-01-01")
    # not counted: archived even though past + active status
    d = db.add_job("D", "Co", url="https://x/4", follow_up_date="2020-01-01")
    db.update_job(d, status="phone_screen")
    db.archive_job(d)
    assert db.count_followups_due(today="2026-06-16") == 1
