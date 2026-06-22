import csv
import json
import pytest

import tracker.db as db
from tracker import service
from rerank.export import export_inbox
from rerank.import_ import import_scores
from models import JobResult


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "tracker.db")
    db.init_db()
    return db.DB_PATH


def _seed():
    db.inbox_add_many([
        JobResult(title="Software Developer", company="Acme", location="Cincinnati, OH",
                  salary_min=None, salary_max=None, description="controls",
                  url="https://x.co/1", source_keyword="", created="2026-06-21",
                  source_api="adzuna", score=70),
        JobResult(title="Controls Engineer", company="Beta", location="Cincinnati, OH",
                  salary_min=None, salary_max=None, description="plc", url="https://x.co/2",
                  source_keyword="", created="2026-06-21", source_api="themuse", score=55),
    ])


def _fill_csv(export_csv, returned_csv, scores: dict):
    """Read the exported CSV, fill new_fit per job_key from `scores`, write a
    returned CSV — simulates the user's AI filling in the carrier."""
    with export_csv.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    with returned_csv.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["job_key", "new_fit", "fit_rationale"])
        w.writeheader()
        for r in rows:
            w.writerow({"job_key": r["job_key"],
                        "new_fit": scores.get(r["job_key"], ""),
                        "fit_rationale": "scored by AI"})


def test_csv_roundtrip_reranks_inbox(tmp_db, tmp_path):
    _seed()
    rows = db.inbox_all()
    paths = export_inbox(rows, tmp_path / "out", fmt="both")
    keys = [r["job_key"] for r in (
        __import__("rerank.schema", fromlist=["row_from_inbox"]).row_from_inbox(x)
        for x in rows)]
    scores = {keys[0]: 95, keys[1]: 40}
    ret = tmp_path / "returned.csv"
    _fill_csv(paths["csv"], ret, scores)
    res = import_scores(ret, service.inbox_rows_by_key(), policy="overwrite")
    assert res.matched == 2 and res.updated == 2 and res.unmatched == []
    by_title = {r["title"]: r["fit"] for r in db.inbox_all()}
    assert by_title["Software Developer"] == 95
    assert by_title["Controls Engineer"] == 40


def test_json_roundtrip_reranks_inbox(tmp_db, tmp_path):
    _seed()
    keys = list(service.inbox_rows_by_key().keys())
    ret = tmp_path / "returned.json"
    ret.write_text(json.dumps([{"job_key": keys[0], "new_fit": 88,
                                "fit_rationale": "great"}]), encoding="utf-8")
    res = import_scores(ret, service.inbox_rows_by_key())
    assert res.updated == 1


def test_double_import_is_idempotent_on_fit(tmp_db, tmp_path):
    _seed()
    keys = list(service.inbox_rows_by_key().keys())
    ret = tmp_path / "r.csv"
    ret.write_text(f"job_key,new_fit\n{keys[0]},77\n", encoding="utf-8")
    import_scores(ret, service.inbox_rows_by_key())
    import_scores(ret, service.inbox_rows_by_key())  # re-import same file
    fits = {r["job_key"]: r["fit"] for r in
            (dict(rr, job_key=k) for k, rr in service.inbox_rows_by_key().items())}
    # fit is the same value after the second import (idempotent beyond a history row)
    target_row = service.inbox_rows_by_key()[keys[0]]
    assert target_row["fit"] == 77
    with db.get_conn() as conn:
        # two history rows (one per import) prove the audit log grew, fit unchanged
        assert conn.execute("SELECT COUNT(*) FROM score_history").fetchone()[0] == 2


def test_undo_after_import_reverts(tmp_db, tmp_path):
    _seed()
    keys = list(service.inbox_rows_by_key().keys())
    ret = tmp_path / "r.csv"
    ret.write_text(f"job_key,new_fit\n{keys[0]},77\n{keys[1]},66\n", encoding="utf-8")
    import_scores(ret, service.inbox_rows_by_key())
    assert service.undo_last_rerank("file_import") == 2
    assert all(r["fit"] == -1 for r in db.inbox_all())
