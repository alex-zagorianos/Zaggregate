"""P0#7 regression: daily_run scores with target_level/semantic_profile/remote_ok,
then scripts.rescore_inbox re-scores every row. Before the fix, rescore called
score_job WITHOUT those three, erasing the exec adjustment daily_run applied at
insert. This proves daily_run-then-rescore is now SCORE-STABLE (rescore routes
through the same score_jobs path)."""
import sqlite3

import pytest

import tracker.db as db
from match.scorer import score_jobs
from models import JobResult
from scripts import rescore_inbox


@pytest.fixture
def tmp_inbox(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "t.db"))
    db.init_db()
    return db.DB_PATH


def _jobs():
    def j(title, url, company="Acme", desc="", loc="Cincinnati, OH"):
        return JobResult(title=title, company=company, location=loc, salary_min=None,
                         salary_max=None, description=desc, url=url, source_keyword="",
                         created="", source_api="t")
    return [
        j("Clinical Data Analyst", "http://x/1"),
        j("VP Clinical Informatics", "http://x/2"),
        j("Director Clinical Informatics", "http://x/3"),
        j("Registered Nurse", "http://x/4", desc="ICU patient care full-time"),
    ]


# Exec keyword set so daily_run's target_level adjustment is ACTIVE -- the exact
# case the old rescore erased.
EXEC_CFG = {
    "keywords": ["VP Clinical Informatics", "Chief Medical Information Officer",
                 "Director Clinical Informatics"],
    "location": "Cincinnati, OH",
    "salary_min": None,
    "exclude_keywords": [],
}


def test_daily_run_then_rescore_is_score_stable(tmp_inbox):
    jobs = _jobs()
    # 1) daily_run scoring path (score_jobs derives target_level/semantic_profile,
    #    passes remote_ok) -> insert into the inbox with those scores.
    score_jobs(jobs, keywords=EXEC_CFG["keywords"], location=EXEC_CFG["location"],
               salary_floor=EXEC_CFG["salary_min"], exclude_keywords=[], remote_ok=True)
    db.inbox_add_many(jobs)

    conn = sqlite3.connect(str(tmp_inbox))
    conn.row_factory = sqlite3.Row
    before = {r["url"]: r["score"] for r in conn.execute("SELECT url, score FROM inbox")}
    conn.close()
    assert before  # rows actually landed

    # 2) rescore with the SAME cfg -> scores must be unchanged (parity).
    res = rescore_inbox.rescore(db_path=tmp_inbox, cfg=EXEC_CFG)

    conn = sqlite3.connect(str(tmp_inbox))
    conn.row_factory = sqlite3.Row
    after = {r["url"]: r["score"] for r in conn.execute("SELECT url, score FROM inbox")}
    conn.close()

    assert after == before, "rescore changed scores daily_run had applied"
    # And the exec adjustment is actually present (VP/Director outrank the analyst),
    # proving the parity isn't just 'both strip it identically'.
    assert after["http://x/2"] > after["http://x/1"]


def test_rescore_twice_is_idempotent(tmp_inbox):
    jobs = _jobs()
    score_jobs(jobs, keywords=EXEC_CFG["keywords"], location=EXEC_CFG["location"],
               salary_floor=None, exclude_keywords=[], remote_ok=True)
    db.inbox_add_many(jobs)
    r1 = rescore_inbox.rescore(db_path=tmp_inbox, cfg=EXEC_CFG)
    r2 = rescore_inbox.rescore(db_path=tmp_inbox, cfg=EXEC_CFG)
    assert r1["after"] == r2["after"]
