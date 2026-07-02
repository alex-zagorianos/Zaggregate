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


# S32 honesty levers (seniority_target / years_cap / title_context_required from
# cfg, remote_regions_ok from preferences 'hard'). daily_run.py:409-419 passes all
# four at insert; the rescore MUST pass them too or the over-target down-nudge,
# title-context cap, and region handling are silently reverted every run. EXEC_CFG
# above sets NONE of these, so it can't catch the drift -- this cfg trips one.
LEVER_CFG = {
    "keywords": ["software engineer"],
    "location": "Cincinnati, OH",
    "salary_min": None,
    "exclude_keywords": [],
    "seniority_target": "entry",
    "years_cap": 3,
}


def test_rescore_preserves_seniority_target_lever(tmp_inbox):
    # An entry-target profile viewing a 'Senior ... 8+ years' role: the insert
    # applies an over-target down-nudge. Before the fix the rescore, which passed
    # NONE of the four levers, re-inflated the score and stripped the note.
    j = JobResult(
        title="Senior Software Engineer", company="Acme", location="Cincinnati, OH",
        salary_min=None, salary_max=None,
        description="8+ years of experience required.", url="http://x/lever",
        source_keyword="", created="", source_api="t")
    score_jobs([j], keywords=LEVER_CFG["keywords"], location=LEVER_CFG["location"],
               salary_floor=None, exclude_keywords=[], remote_ok=True,
               seniority_target=LEVER_CFG["seniority_target"],
               years_cap=LEVER_CFG["years_cap"])
    db.inbox_add_many([j])

    conn = sqlite3.connect(str(tmp_inbox))
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT score, score_notes FROM inbox").fetchone()
    before, before_notes = row["score"], row["score_notes"]
    conn.close()
    assert "over-target" in before_notes  # insert actually tripped the lever

    rescore_inbox.rescore(db_path=tmp_inbox, cfg=LEVER_CFG)

    conn = sqlite3.connect(str(tmp_inbox))
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT score, score_notes FROM inbox").fetchone()
    after, after_notes = row["score"], row["score_notes"]
    conn.close()

    assert after == before, "rescore drifted the seniority-target down-nudge"
    assert "over-target" in after_notes, "rescore erased the 'over-target' note"
