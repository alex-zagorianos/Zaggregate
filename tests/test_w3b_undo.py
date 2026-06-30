"""Wave 3b - undo reverts the whole rerank batch and clears the Top-Picks rank."""
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


def _seed(n=3):
    db.inbox_add_many([
        JobResult(title=f"Role {i}", company=f"Co{i}", location="Cincinnati, OH",
                  salary_min=None, salary_max=None, description="x",
                  url=f"https://x.co/{i}", source_keyword="", created="2026-06-30",
                  source_api="adzuna", score=60) for i in range(n)])
    return db.inbox_all()


def test_undo_reverts_whole_batch_and_clears_rank(tmp_db):
    rows = _seed(3)
    updates = [{"id": int(r["id"]), "new_fit": 90,
                "extras": json.dumps(service.rank_patch(i + 1, "b1"))}
               for i, r in enumerate(rows)]
    service.apply_rerank_scores(updates)
    assert all(r["fit"] == 90 for r in db.inbox_all())
    assert len(service.top_picks()) == 3

    n = service.undo_last_rerank("file_import")
    assert n == 3
    assert all(r["fit"] == -1 for r in db.inbox_all())  # pre-rerank default
    assert service.top_picks() == []
