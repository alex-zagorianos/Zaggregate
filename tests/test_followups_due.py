import datetime

import pytest

from tracker import db


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "tracker.db")
    db.init_db()
    return db.DB_PATH


TODAY = datetime.date(2026, 6, 24)


def _d(delta):
    return (TODAY + datetime.timedelta(days=delta)).isoformat()


def test_picks_overdue_followup_and_approaching_deadline(tmp_db):
    a = db.add_job("Controls Eng", "Acme", url="u1")
    db.update_job(a, status="applied", follow_up_date=_d(-1))      # overdue follow-up
    b = db.add_job("Software Eng", "Beta", url="u2")
    db.update_job(b, status="applied", follow_up_date=_d(+1))      # not due yet
    c = db.add_job("ML Eng", "Gamma", url="u3")
    db.update_job(c, status="interested", deadline=_d(0))          # deadline today

    due = db.followups_due(today=TODAY)
    ids = [d["id"] for d in due]
    assert a in ids and c in ids and b not in ids
    kinds = {d["id"]: d["due_kind"] for d in due}
    assert kinds[a] == "follow-up" and kinds[c] == "deadline"
    assert all("due_date" in d for d in due)


def test_within_days_window(tmp_db):
    b = db.add_job("Software Eng", "Beta", url="u2")
    db.update_job(b, status="applied", follow_up_date=_d(+1))
    assert db.followups_due(today=TODAY) == []                     # tomorrow not due today
    assert [d["id"] for d in db.followups_due(within_days=3, today=TODAY)] == [b]


def test_deadlines_can_be_excluded(tmp_db):
    c = db.add_job("ML Eng", "Gamma", url="u3")
    db.update_job(c, status="interested", deadline=_d(0))
    assert db.followups_due(today=TODAY, include_deadlines=False) == []


def test_archived_and_wrong_status_excluded(tmp_db):
    a = db.add_job("Old", "Acme", url="u1")
    db.update_job(a, status="applied", follow_up_date=_d(-2))
    db.archive_job(a)
    assert db.followups_due(today=TODAY) == []
