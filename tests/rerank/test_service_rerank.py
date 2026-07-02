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


def test_inbox_rows_by_key_keys_by_job_key(tmp_db):
    db.inbox_add_many([_job("https://x.co/1")])
    m = service.inbox_rows_by_key()
    assert len(m) == 1
    (key, row), = m.items()
    assert key and "id" in row and "fit" in row


def test_apply_rerank_scores_writes_fit_and_history(tmp_db):
    db.inbox_add_many([_job("https://x.co/1")])
    iid = db.inbox_all()[0]["id"]
    n = service.apply_rerank_scores(
        [{"id": iid, "new_fit": 91, "fit_rationale": "strong"}], source="file_import")
    assert n == 1
    row = db.inbox_all()[0]
    assert row["fit"] == 91 and row["fit_why"] == "strong"
    with db.get_conn() as conn:
        assert conn.execute("SELECT COUNT(*) FROM score_history WHERE source='file_import'"
                            ).fetchone()[0] == 1


def test_apply_rerank_scores_persists_extras(tmp_db):
    db.inbox_add_many([_job("https://x.co/1")])
    iid = db.inbox_all()[0]["id"]
    service.apply_rerank_scores(
        [{"id": iid, "new_fit": 80, "fit_rationale": "ok", "extras": '{"tags":"plc"}'}])
    with db.get_conn() as conn:
        raw = conn.execute("SELECT extras FROM inbox WHERE id=?", (iid,)).fetchone()["extras"]
    import json
    extras = json.loads(raw)
    # The imported tags are preserved...
    assert extras["tags"] == "plc"
    # ...and, since this import carried NO new_rank, the S32/L2 fit fallback now
    # ALSO derives a shortlist rank/rec_batch so Top Picks isn't left empty.
    assert extras["rank"] == 1 and extras["rec_batch"]


def test_undo_last_rerank_reverts(tmp_db):
    db.inbox_add_many([_job("https://x.co/1")])
    iid = db.inbox_all()[0]["id"]
    service.apply_rerank_scores([{"id": iid, "new_fit": 91, "fit_rationale": "x"}])
    assert service.undo_last_rerank("file_import") == 1
    assert db.inbox_all()[0]["fit"] == -1


def test_file_import_without_rank_still_fills_top_picks(tmp_db):
    """S32/L2: a file import that writes new_fit but NO new_rank used to leave the
    Top Picks tab silently empty (only the clipboard route derived a shortlist).
    apply_rerank_scores now falls back to ranking by new_fit descending."""
    db.inbox_add_many([_job("https://x.co/1", title="A"),
                       _job("https://x.co/2", title="B"),
                       _job("https://x.co/3", title="C")])
    ids = [r["id"] for r in db.inbox_all()]
    service.apply_rerank_scores(
        [{"id": ids[0], "new_fit": 70}, {"id": ids[1], "new_fit": 90},
         {"id": ids[2], "new_fit": 55}], source="file_import")
    picks = service.top_picks(0)
    # Populated (was [] before the fix), ranked by fit descending.
    assert [p["title"] for p in picks] == ["B", "A", "C"]
    assert [p["rank"] for p in picks] == [1, 2, 3]


def test_file_import_with_rank_does_not_override_with_fit(tmp_db):
    """When the import DID supply an explicit new_rank, the fit fallback must NOT
    kick in and reorder — the AI's chosen rank wins."""
    import json
    db.inbox_add_many([_job("https://x.co/1", title="A"),
                       _job("https://x.co/2", title="B")])
    ids = [r["id"] for r in db.inbox_all()]
    batch = service.new_rec_batch()
    service.apply_rerank_scores(
        [{"id": ids[0], "new_fit": 60,
          "extras": json.dumps(service.rank_patch(1, batch))},
         {"id": ids[1], "new_fit": 99,
          "extras": json.dumps(service.rank_patch(2, batch))}],
        source="file_import")
    picks = service.top_picks(0)
    # Explicit rank (A=1, B=2) preserved, though B has the higher fit.
    assert [p["title"] for p in sorted(picks, key=lambda x: x["rank"])] == ["A", "B"]


def test_import_to_top_picks_end_to_end(tmp_db, tmp_path):
    from rerank.import_ import import_scores
    db.inbox_add_many([_job("https://x.co/1", title="A"),
                       _job("https://x.co/2", title="B")])
    m = service.inbox_rows_by_key()
    keys = list(m.keys())
    p = tmp_path / "ret.csv"
    p.write_text("job_key,new_fit,new_rank\n"
                 f"{keys[0]},90,2\n{keys[1]},95,1\n", encoding="utf-8")
    res = import_scores(p, m)
    assert res.updated == 2
    picks = service.top_picks(0)
    assert [pp["rank"] for pp in picks] == [1, 2]
    assert picks[0]["fit"] == 95
