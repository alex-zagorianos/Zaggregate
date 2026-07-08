"""compute_marginal_yield / low_activity_terms -- Phase 6 low-yield flagging.

Nothing here ever changes a term's status; flagging only surfaces a UI nudge
(the same "drop != hide" doctrine gate.py uses for scoring). Deactivation
stays an explicit user action elsewhere.
"""
from datetime import datetime, timedelta, timezone

import pytest

from tracker import db
from search.discovery import pool
from search.discovery import flag


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "tracker.db")
    db.init_db()
    return tmp_path


def _activate_with_age(term, days_ago, yield_count=0):
    """Create (if needed) + activate a term, then backdate activated_at."""
    pool.upsert_terms([{"term": term, "tier": "core", "source": "onet"}])
    pool.set_status(term, "active")
    pool.set_yield(term, yield_count, "test")
    backdated = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
    with db.get_conn() as conn:
        conn.execute("UPDATE keyword_pool SET activated_at=? WHERE term=?",
                     (backdated, term))
        conn.commit()


def test_low_yield_requires_min_activation_age(tmp_db):
    _activate_with_age("Small Engine Repair Tech", days_ago=2, yield_count=0)
    too_new = flag.compute_marginal_yield("Small Engine Repair Tech", min_age_days=7)
    assert too_new["eligible"] is False
    assert too_new["low_activity"] is False

    _activate_with_age("Small Engine Repair Tech", days_ago=10, yield_count=0)
    aged = flag.compute_marginal_yield("Small Engine Repair Tech", min_age_days=7)
    assert aged["eligible"] is True
    assert aged["low_activity"] is True
    assert aged["age_days"] >= 7


def test_low_activity_never_changes_status(tmp_db):
    _activate_with_age("Low Yield Term", days_ago=30, yield_count=0)
    _activate_with_age("Healthy Term", days_ago=30, yield_count=15)

    before = {r["term"]: r["status"] for r in pool.get_pool()}
    flagged = flag.low_activity_terms()

    assert any(r["term"] == "Low Yield Term" for r in flagged)
    assert not any(r["term"] == "Healthy Term" for r in flagged)

    after = {r["term"]: r["status"] for r in pool.get_pool()}
    assert before == after
    assert all(status == "active" for status in after.values())


def test_compute_marginal_yield_ignores_non_active(tmp_db):
    pool.upsert_terms([{"term": "Just Suggested", "tier": "exploratory", "source": "ai"}])
    result = flag.compute_marginal_yield("Just Suggested")
    assert result["eligible"] is False
    assert result["low_activity"] is False

    # unknown term is equally inert, never raises
    unknown = flag.compute_marginal_yield("Nonexistent Term")
    assert unknown["eligible"] is False
    assert unknown["low_activity"] is False
