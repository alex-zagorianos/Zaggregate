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
        assert conn.execute("SELECT extras FROM inbox WHERE id=?",
                            (iid,)).fetchone()["extras"] == '{"tags":"plc"}'


def test_undo_last_rerank_reverts(tmp_db):
    db.inbox_add_many([_job("https://x.co/1")])
    iid = db.inbox_all()[0]["id"]
    service.apply_rerank_scores([{"id": iid, "new_fit": 91, "fit_rationale": "x"}])
    assert service.undo_last_rerank("file_import") == 1
    assert db.inbox_all()[0]["fit"] == -1


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
