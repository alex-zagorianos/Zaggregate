import sqlite3
import pytest

import tracker.db as db


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "tracker.db")
    return db.DB_PATH


def test_status_history_records_transitions(tmp_db):
    """Status changes are recorded with old/new pairs and timestamps."""
    db.init_db()
    job_id = db.add_job("Software Engineer", "Acme Corp", status="applied")

    # Three distinct status transitions
    db.update_job(job_id, status="phone_screen")
    db.update_job(job_id, status="interview")
    db.update_job(job_id, status="offer")

    with db.get_conn() as conn:
        rows = conn.execute(
            "SELECT old_status, new_status FROM status_history WHERE job_id=? ORDER BY id",
            (job_id,)
        ).fetchall()

    assert len(rows) == 3
    assert rows[0]["old_status"] == "applied"
    assert rows[0]["new_status"] == "phone_screen"
    assert rows[1]["old_status"] == "phone_screen"
    assert rows[1]["new_status"] == "interview"
    assert rows[2]["old_status"] == "interview"
    assert rows[2]["new_status"] == "offer"


def test_status_history_skips_duplicate_status(tmp_db):
    """Updating to the same status does NOT create a history row."""
    db.init_db()
    job_id = db.add_job("Data Scientist", "DataCo", status="applied")

    db.update_job(job_id, status="interview")
    db.update_job(job_id, status="interview")  # Same status again

    with db.get_conn() as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM status_history WHERE job_id=?",
            (job_id,)
        ).fetchone()[0]

    assert count == 1


def test_status_history_no_row_when_status_unchanged(tmp_db):
    """Updating other fields without touching status adds no history row."""
    db.init_db()
    job_id = db.add_job("Frontend Dev", "WebCorp", status="applied")

    db.update_job(job_id, notes="Spoke with recruiter", follow_up_date="2026-06-20")

    with db.get_conn() as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM status_history WHERE job_id=?",
            (job_id,)
        ).fetchone()[0]

    assert count == 0
