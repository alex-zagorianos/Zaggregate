"""Freshness deltas are wired non-destructively: daily_run marks jobs new since
the last run (search/freshness baseline), inbox_add_many stamps those rows'
extras with a new_batch, and the GUI's "New only" filter reads the latest batch.
No schema change — rides the existing extras JSON like Top Picks' rank."""
import json
import pytest

import tracker.db as db
from models import JobResult


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "tracker.db")
    db.init_db()
    return db.DB_PATH


def _job(url, is_new, title="Controls Engineer"):
    j = JobResult(title=title, company="Acme", location="Cincinnati, OH",
                  salary_min=None, salary_max=None, description="plc", url=url,
                  source_keyword="", created="2026-06-21", source_api="careers", score=80)
    j.is_new = is_new
    return j


def test_inbox_add_many_stamps_new_batch_only_on_new_rows(tmp_db):
    batch = "2026-06-24T10:00:00+00:00"
    db.inbox_add_many([_job("https://x/1", True), _job("https://x/2", False)],
                      new_batch=batch)
    rows = {r["url"]: r for r in db.inbox_all()}
    e1 = json.loads(rows["https://x/1"]["extras"] or "{}")
    assert e1.get("new_batch") == batch          # new job stamped
    assert not (rows["https://x/2"]["extras"] or "")  # non-new job untouched


def test_inbox_add_many_no_batch_is_noop(tmp_db):
    # Back-compat: existing callers that pass no new_batch never stamp extras.
    db.inbox_add_many([_job("https://x/9", True)])
    assert not (db.inbox_all()[0]["extras"] or "")


def test_gui_new_batch_helpers():
    from gui import _row_new_batch, _latest_new_batch, _is_new_row
    rows = [
        {"extras": '{"new_batch": "2026-06-24T10:00:00+00:00"}'},
        {"extras": '{"new_batch": "2026-06-23T10:00:00+00:00"}'},
        {"extras": '{"tags": ["plc"]}'},   # extras without new_batch
        {"extras": None},                  # no extras
        {"extras": "not json"},            # malformed
    ]
    latest = _latest_new_batch(rows)
    assert latest == "2026-06-24T10:00:00+00:00"
    assert _is_new_row(rows[0], latest) is True
    assert _is_new_row(rows[1], latest) is False   # older batch is not "new"
    assert _is_new_row(rows[2], latest) is False
    assert _is_new_row(rows[3], latest) is False
    assert _row_new_batch(rows[4]) == ""
    # No row stamped -> nothing is "new".
    assert _latest_new_batch([{"extras": None}]) is None


def test_freshness_marks_job_is_new_against_baseline(tmp_path, monkeypatch):
    import search.freshness as freshness
    monkeypatch.setattr(freshness.config, "USER_DATA_DIR", tmp_path)
    # job_key is URL-independent (company|soc|loc|title_core), so the "new" job
    # must differ in a key field, not just its URL — a re-post of the same role
    # at a new URL is correctly NOT new.
    seen = _job("https://x/seen", False, title="Controls Engineer")
    fresh = _job("https://x/fresh", False, title="Mechatronics Engineer")
    freshness.save_keys("daily:test", {seen.job_key})
    prev = freshness.load_prev_keys("daily:test")
    for r in (seen, fresh):
        r.is_new = r.job_key not in prev
    assert seen.is_new is False
    assert fresh.is_new is True
