import pytest

import tracker.db as db
import tracker.service as svc
from match import facts as F
from models import JobResult

PREFS = {"profile_md": "controls + embedded build roles", "hard": {}}
CFG = {"keywords": ["controls engineer"], "salary_min": 85000,
       "exclude_titles": ["ai", "machine learning"]}


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "tracker.db")
    db.init_db()
    return db.DB_PATH


def _rows():
    return [
        {"id": 1, "title": "Controls Engineer", "company": "Acme", "location": "Cincinnati",
         "url": "https://x/1", "salary_text": "$100k",
         "description": "design and develop embedded firmware, real-time motion control",
         "board_count": 10, "created": ""},
        {"id": 2, "title": "Electrical Engineer Intern", "company": "B", "location": "Austin",
         "url": "https://x/2", "salary_text": "",
         "description": "embedded systems internship", "board_count": -1, "created": ""},
    ]


def test_compact_prompt_gates_and_carries_ids(monkeypatch, tmp_path):
    monkeypatch.setattr(F, "_cache_dir", lambda: tmp_path)
    prompt, kept, dropped = svc.compact_fit_prompt_for_rows(_rows(), prefs=PREFS, cfg=CFG)
    assert [j.title for j in kept] == ["Controls Engineer"]
    assert kept[0].job_id == "1"                      # row id carried for write-back
    assert "Facts:" in prompt and "Description:" not in prompt
    assert dropped[0]["id"] == 2 and dropped[0]["title"] == "Electrical Engineer Intern"
    assert "internship" in dropped[0]["reasons"]


def test_mark_inbox_gated_writes_low_fit(tmp_db, monkeypatch, tmp_path):
    monkeypatch.setattr(F, "_cache_dir", lambda: tmp_path)
    jobs = [JobResult("Electrical Engineer Intern", "B", "Austin", None, None,
                      "embedded internship", "https://x/2", "", "", "test", score=60)]
    db.inbox_add_many(jobs)
    row = db.inbox_all()[0]
    n = svc.mark_inbox_gated([{"id": row["id"], "title": row["title"],
                               "company": row["company"], "reasons": ["internship"]}])
    assert n == 1
    after = {r["id"]: r for r in db.inbox_all()}[row["id"]]
    assert after["fit"] == svc._GATE_FIT
    assert after["fit_why"].startswith("Auto-filtered:") and "internship" in after["fit_why"]


def test_mark_inbox_gated_skips_idless(monkeypatch, tmp_path):
    monkeypatch.setattr(F, "_cache_dir", lambda: tmp_path)
    assert svc.mark_inbox_gated([{"id": None, "reasons": ["x"]}]) == 0
