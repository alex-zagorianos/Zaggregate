"""Undo parity + partial coverage across every AI-scoring route (C2 / P4 items 3-4).

  * inbox_set_fit returns True/False (row actually updated); a missing id is a
    silent no-op that now reports False (phantom-applied fix).
  * score_inbox_from_reply mints ONE shared batch, tags source ('bridge'/'api'),
    and returns (applied, missed).
  * inbox_undo_last_rerank('any') reverts the whole newest batch regardless of
    which route wrote it (bridge / api / mcp).
"""
import json

import pytest

import tracker.db as db
import tracker.service as svc
from models import JobResult
import claude_bridge


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "tracker.db")
    db.init_db()
    return db.DB_PATH


def _job(title, url, score=70):
    return JobResult(title=title, company="Acme", location="Cincinnati, OH",
                     salary_min=90000, salary_max=120000, description="controls",
                     url=url, source_keyword="", created="2026-06-01",
                     source_api="adzuna", score=score)


def _reply(jobs, fits):
    return json.dumps([{"token": claude_bridge.fit_token(j), "fit": f, "why": "ok"}
                       for j, f in zip(jobs, fits)])


# ── inbox_set_fit return indicator ────────────────────────────────────────────

def test_inbox_set_fit_returns_true_on_hit(tmp_db):
    db.inbox_add_many([_job("A", "https://x/1")])
    iid = db.inbox_all()[0]["id"]
    assert db.inbox_set_fit(iid, 80, "why") is True
    assert db.inbox_all()[0]["fit"] == 80


def test_inbox_set_fit_returns_false_on_missing(tmp_db):
    # Missing id: no update, no phantom score_history row.
    assert db.inbox_set_fit(999999, 80, "why", source="mcp") is False
    with db.get_conn() as conn:
        n = conn.execute("SELECT COUNT(*) FROM score_history").fetchone()[0]
    assert n == 0


# ── partial coverage return ───────────────────────────────────────────────────

def test_score_inbox_from_reply_reports_missed(tmp_db):
    db.inbox_add_many([_job("A", "https://x/1"), _job("B", "https://x/2"),
                       _job("C", "https://x/3")])
    jobs = svc.jobs_from_rows(db.inbox_all())
    # Only score the first two — the reply omits job C.
    applied, missed = svc.score_inbox_from_reply(jobs, _reply(jobs[:2], [90, 70]))
    assert applied == 2
    assert [m["title"] for m in missed] == ["C"]


# ── shared batch: one undo reverts the whole route's set ──────────────────────

def test_bridge_batch_is_atomic_undo_any(tmp_db):
    db.inbox_add_many([_job("A", "https://x/1"), _job("B", "https://x/2")])
    jobs = svc.jobs_from_rows(db.inbox_all())
    svc.score_inbox_from_reply(jobs, _reply(jobs, [90, 70]), source="bridge")
    assert {r["fit"] for r in db.inbox_all()} == {90, 70}
    # scope='any' reverts the whole bridge batch (both rows), not zero.
    n = svc.undo_last_rerank("any")
    assert n == 2
    assert all(r["fit"] == -1 for r in db.inbox_all())


def test_undo_any_reverts_newest_route_only(tmp_db):
    """Two routes score in sequence; undo('any') reverts only the NEWEST batch,
    leaving the earlier route's scores intact."""
    db.inbox_add_many([_job("A", "https://x/1"), _job("B", "https://x/2")])
    jobs = svc.jobs_from_rows(db.inbox_all())
    # Route 1 (bridge) scores both.
    svc.score_inbox_from_reply(jobs, _reply(jobs, [90, 80]), source="bridge")
    # Route 2 (api) re-scores just job A with a fresh (newer) batch.
    svc.score_inbox_from_reply([jobs[0]], _reply([jobs[0]], [50]), source="api")
    by_id = {r["id"]: r for r in db.inbox_all()}
    assert by_id[int(jobs[0].job_id)]["fit"] == 50
    # Undo the newest batch -> job A goes back to the bridge's 90, B untouched.
    n = svc.undo_last_rerank("any")
    assert n == 1
    by_id = {r["id"]: r for r in db.inbox_all()}
    assert by_id[int(jobs[0].job_id)]["fit"] == 90
    assert by_id[int(jobs[1].job_id)]["fit"] == 80


def test_api_route_undoable(tmp_db):
    db.inbox_add_many([_job("A", "https://x/1")])
    jobs = svc.jobs_from_rows(db.inbox_all())
    svc.score_inbox_from_reply(jobs, _reply(jobs, [88]), source="api")
    assert db.inbox_all()[0]["fit"] == 88
    assert svc.undo_last_rerank("any") == 1
    assert db.inbox_all()[0]["fit"] == -1


def test_mcp_shared_batch_undoable(tmp_db):
    import pytest as _pt
    _pt.importorskip("mcp")
    import mcp_server
    db.inbox_add_many([_job("A", "https://x/1"), _job("B", "https://x/2")])
    ids = [r["id"] for r in db.inbox_all()]
    out = mcp_server.set_fit_scores([
        {"id": ids[0], "fit": 90, "rationale": "x", "rank": 1},
        {"id": ids[1], "fit": 70, "rationale": "y", "rank": 2},
        {"id": 987654, "fit": 60, "rationale": "phantom"},   # missing -> not applied
    ])
    assert out["applied"] == 2 and out["missed"] == 1
    assert {r["fit"] for r in db.inbox_all()} == {90, 70}
    # One shared MCP batch -> undo('any') reverts both.
    assert svc.undo_last_rerank("any") == 2
    assert all(r["fit"] == -1 for r in db.inbox_all())
