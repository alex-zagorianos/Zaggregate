"""Regression tests for the session-25 adversarial-review findings.
See brain/REVIEW-REPORT-2026-07-01-session25.md."""
import pytest

import tracker.db as db
from models import JobResult
from match.ghost import ghost_score


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "tracker.db")
    db.init_db()
    return db.DB_PATH


def _job(url, valid_through="", title="Nurse", company="Acme"):
    return JobResult(title=title, company=company, location="Cincinnati, OH",
                     salary_min=None, salary_max=None, description="care",
                     url=url, source_keyword="", created="", source_api="careers",
                     valid_through=valid_through)


# ── Finding 4: urls_not_seen must chunk to stay under SQLite's variable cap ─────
def test_urls_not_seen_handles_large_batch(tmp_db):
    # >999 candidates would blow SQLite's compiled MAX_VARIABLE_NUMBER on old
    # builds without chunking. All-unseen -> all returned, no exception.
    urls = [f"https://x/{i}" for i in range(2500)]
    out = db.urls_not_seen(urls)
    assert out == set(urls)


# ── Finding 5: valid_through persists to inbox extras and ghost reads it ────────
def _iso_days_ago(n):
    from datetime import datetime, timedelta, timezone
    return (datetime.now(timezone.utc) - timedelta(days=n)).date().isoformat()


def test_valid_through_persisted_and_ghost_sees_it(tmp_db):
    db.inbox_add_many([_job("https://x/expired", valid_through=_iso_days_ago(5))])
    rows = db.inbox_all()
    row = next(r for r in rows if r["url"] == "https://x/expired")
    # It's stored in the extras JSON (schema-free, no new column)...
    import json
    assert json.loads(row["extras"]).get("valid_through") == _iso_days_ago(5)
    # ...and ghost_score, given the inbox row dict, now fires the expired signal.
    g = ghost_score(row)
    assert g["level"] == "stale"
    assert any("expired" in r for r in g["reasons"])
