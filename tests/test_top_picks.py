import json
import pytest
import tracker.db as db
from tracker import service
from models import JobResult


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "tracker.db")
    db.init_db()
    return db.DB_PATH


def _job(url, title="Software Developer", company="Acme"):
    return JobResult(title=title, company=company, location="Cincinnati, OH",
                     salary_min=None, salary_max=None, description="controls",
                     url=url, source_keyword="", created="2026-06-21",
                     source_api="adzuna", score=70)


def test_merge_extras_preserves_other_keys(tmp_db):
    db.inbox_add_many([_job("https://x/1")])
    iid = db.inbox_all()[0]["id"]
    db.inbox_set_extras(iid, '{"tags":"plc"}')
    db.inbox_merge_extras(iid, {"rank": 1, "rec_batch": "B1"})
    extras = json.loads(db.inbox_all()[0]["extras"])
    assert extras == {"tags": "plc", "rank": 1, "rec_batch": "B1"}


def test_merge_extras_tolerates_garbage_blob(tmp_db):
    db.inbox_add_many([_job("https://x/1")])
    iid = db.inbox_all()[0]["id"]
    db.inbox_set_extras(iid, "not json")
    db.inbox_merge_extras(iid, {"rank": 2, "rec_batch": "B"})
    assert json.loads(db.inbox_all()[0]["extras"]) == {"rank": 2, "rec_batch": "B"}


def test_read_rank_missing_is_minus_one(tmp_db):
    db.inbox_add_many([_job("https://x/1")])
    assert service.read_rank(db.inbox_all()[0]) == -1


def test_top_picks_orders_by_rank_and_caps(tmp_db):
    db.inbox_add_many([_job("https://x/1", "A"), _job("https://x/2", "B"),
                       _job("https://x/3", "C")])
    rows = db.inbox_all()
    b = service.new_rec_batch()
    db.inbox_merge_extras(rows[0]["id"], service.rank_patch(2, b))
    db.inbox_merge_extras(rows[1]["id"], service.rank_patch(1, b))
    db.inbox_merge_extras(rows[2]["id"], service.rank_patch(3, b))
    assert [p["rank"] for p in service.top_picks(2)] == [1, 2]
    assert len(service.top_picks(0)) == 3


def test_top_picks_latest_batch_supersedes(tmp_db):
    db.inbox_add_many([_job("https://x/1", "A"), _job("https://x/2", "B")])
    rows = db.inbox_all()
    db.inbox_merge_extras(rows[0]["id"],
                          service.rank_patch(1, "2026-06-22T00:00:00+00:00"))
    db.inbox_merge_extras(rows[1]["id"],
                          service.rank_patch(1, "2026-06-22T01:00:00+00:00"))
    picks = service.top_picks(0)
    assert len(picks) == 1 and picks[0]["id"] == rows[1]["id"]


def test_top_picks_empty_when_unranked(tmp_db):
    db.inbox_add_many([_job("https://x/1")])
    assert service.top_picks() == []


@pytest.fixture
def unbootstrapped_db(tmp_path, monkeypatch):
    """Point DB_PATH at a fresh path but do NOT run init_db(), so the ``inbox``
    table does not exist — the exact state a brand-new data dir is in before any
    project/daily-run creates the schema (get_conn does not init). Regression
    guard for D5.3: inbox reads must degrade to empty, never raise
    OperationalError('no such table: inbox')."""
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "tracker.db")
    return db.DB_PATH


def test_inbox_reads_tolerate_missing_table(unbootstrapped_db):
    # None of these may raise on a fresh, un-migrated data dir.
    assert db.inbox_all() == []
    assert db.inbox_all(order="score") == []
    assert db.inbox_count() == 0
    assert db.inbox_company_counts() == {}
    assert db.inbox_company_display_names() == {}
    assert db.inbox_search("engineer") == []
    assert service.top_picks() == []
    assert service.top_picks(0) == []
