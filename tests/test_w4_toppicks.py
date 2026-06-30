"""Wave 4 - Top Picks fills from the clipboard scoring pass; export prompt contract."""
import pytest

import tracker.db as db
from tracker import service
from models import JobResult
import claude_bridge
from rerank.schema import build_prompt


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "tracker.db")
    db.init_db()
    return db.DB_PATH


def test_clipboard_scoring_fills_top_picks(tmp_db):
    db.inbox_add_many([
        JobResult(title="Controls Engineer", company="Acme", location="Cincinnati, OH",
                  salary_min=None, salary_max=None, description="plc", url="https://x.co/1",
                  source_keyword="", created="2026-06-30", source_api="adzuna", score=70),
        JobResult(title="Automation Engineer", company="Beta", location="Cincinnati, OH",
                  salary_min=None, salary_max=None, description="robots", url="https://x.co/2",
                  source_keyword="", created="2026-06-30", source_api="adzuna", score=60)])
    jobs = service.jobs_from_rows(db.inbox_all())
    # Build a reply that echoes each job's token (token-verified mapping).
    import json
    objs = [{"token": claude_bridge.fit_token(j), "fit": fit, "why": "ok"}
            for j, fit in zip(jobs, (85, 70))]
    n = service.score_inbox_from_reply(jobs, json.dumps(objs))
    assert n == 2
    picks = service.top_picks()
    assert [p["rank"] for p in picks] == [1, 2]
    assert picks[0]["fit"] == 85  # best fit ranked first


def test_export_prompt_has_no_array_json_contract():
    p = build_prompt("I want controls roles in Cincinnati.")
    assert "new_fit" in p and "new_rank" in p          # the CSV contract stays
    assert "JSON array" not in p                         # the bridge contract is gone
    assert '"token"' not in p
