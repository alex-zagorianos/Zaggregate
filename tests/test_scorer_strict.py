"""Auto-strict scoring: off-target titles are downranked (not hidden) via a
title-relevance gate, a title blocklist, and an optional seniority blocklist."""
from match import scorer
from models import JobResult

KW = ["controls engineer", "automation engineer", "mechanical engineer"]
LOC = "Cincinnati, OH"


def _job(title, url="http://x"):
    return JobResult(title=title, company="C", location=LOC, salary_min=None,
                     salary_max=None, description="", url=url, source_keyword="",
                     created="", source_api="t")


def test_off_target_title_downranked_below_on_target():
    on, _ = scorer.score_job(_job("Controls Engineer"), keywords=KW, location=LOC)
    off, notes = scorer.score_job(_job("AI Engineer", "http://y"), keywords=KW, location=LOC)
    assert off < on
    assert "title-miss" in notes  # title matched no search query


EXCL = ["ai", "machine learning", "data scientist", "frontend"]


def test_exclude_title_blocklist_hits_ai_ml():
    _, notes = scorer.score_job(_job("Machine Learning Engineer"), keywords=KW,
                                location=LOC, exclude_titles=EXCL)
    assert "machine learning" in notes.lower()


def test_exclude_title_word_boundary_no_false_positive():
    # "ai" must not match inside "Maintenance" — no excl-title hit despite the list.
    _, notes = scorer.score_job(_job("Maintenance Engineer"), keywords=KW,
                                location=LOC, exclude_titles=EXCL)
    assert "excl-title" not in notes


def test_seniority_exclude_downranks_when_configured():
    base, _ = scorer.score_job(_job("Controls Engineer"), keywords=KW, location=LOC,
                               seniority_exclude=["manager"])
    mgr, notes = scorer.score_job(_job("Controls Engineering Manager", "http://z"),
                                  keywords=KW, location=LOC, seniority_exclude=["manager"])
    assert mgr < base
    assert "manager" in notes.lower()


def test_on_target_title_not_penalized():
    _, notes = scorer.score_job(_job("Senior Controls Engineer"), keywords=KW, location=LOC)
    assert "title-miss" not in notes


def test_not_query_in_keyword_triggers_gate():
    # keyword excludes 'senior'; a senior title satisfies no query -> title-miss
    _, notes = scorer.score_job(_job("Senior Controls Engineer"), location=LOC,
                                keywords=['"controls engineer" NOT senior'])
    assert "title-miss" in notes
