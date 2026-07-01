"""The deterministic scorer had no seniority dimension, so an exec seeker's real
target-level roles (VP/Director/CMIO) could not outrank clearly-below keyword
matches. These tests pin the new bounded target-level adjustment — and that it is
a strict no-op for IC / engineering searches (Alex byte-identical)."""
from models import JobResult
from match import scorer


def _job(title, desc="Leading analytics strategy and governance."):
    return JobResult(title=title, company="X", location="Remote", salary_min=None,
                     salary_max=None, description=desc, url="http://x/" + title.replace(" ", ""),
                     source_keyword="", created="", job_id=title, source_api="t")


DAD_KW = ["VP Clinical Informatics", "Chief Medical Information Officer",
          "Director Clinical Informatics", "VP Health IT"]
ALEX_KW = ["controls engineer", "embedded systems engineer", "automation engineer"]


def test_target_level_exec_for_dad_ic_for_alex():
    assert scorer._target_level(DAD_KW) == 5      # director/VP/chief tier
    assert scorer._target_level(ALEX_KW) == 2     # mid (no seniority tokens)


def test_adjustment_neutral_for_ic_target_same_or_lower_level():
    # An IC target (below manager) leaves same/lower-level postings untouched, so an
    # ordinary IC/senior search's non-management results are unchanged.
    assert scorer._seniority_fit_adj("Senior Controls Engineer", 2) == 0
    assert scorer._seniority_fit_adj("Controls Engineer", 2) == 0
    assert scorer._seniority_fit_adj("Junior Controls Engineer", 2) == 0


def test_adjustment_penalizes_management_for_ic_target():
    # Symmetric branch (P2): an IC seeker's manager/director postings are off-target
    # and take a mirror penalty (~-10/-14) so they stop tying true IC roles.
    assert scorer._seniority_fit_adj("Engineering Manager", 2) == -10
    assert scorer._seniority_fit_adj("Director of Engineering", 2) == -14
    assert scorer._seniority_fit_adj("VP of Engineering", 2) == -14
    # target None (no keywords) stays neutral regardless of the posting level.
    assert scorer._seniority_fit_adj("Engineering Manager", None) == 0


def test_adjustment_rewards_target_level_penalizes_junior_for_exec():
    tgt = 5  # exec seeker
    assert scorer._seniority_fit_adj("Chief Medical Information Officer", tgt) == 15
    assert scorer._seniority_fit_adj("VP, Clinical Informatics", tgt) == 15
    assert scorer._seniority_fit_adj("Senior Manager, Health Data", tgt) == 4     # -1 tier
    assert scorer._seniority_fit_adj("Clinical Data Analyst", tgt) == -16          # mid, junior
    assert scorer._seniority_fit_adj("Health Informatics Intern", tgt) == -16


def test_score_jobs_lifts_exec_role_for_exec_seeker():
    jobs = [_job("Clinical Data Analyst"), _job("VP Clinical Informatics")]
    scorer.score_jobs(jobs, keywords=DAD_KW, location="Cincinnati")
    by_title = {j.title: j.score for j in jobs}
    assert by_title["VP Clinical Informatics"] > by_title["Clinical Data Analyst"]


def test_score_is_byte_identical_for_ic_search():
    # Same jobs scored under an IC keyword set must be unchanged vs a run with the
    # seniority feature effectively off (target below manager). We assert the notes
    # carry no 'level' adjustment token for an IC search.
    jobs = [_job("Senior Controls Engineer"), _job("Controls Engineer")]
    scorer.score_jobs(jobs, keywords=ALEX_KW, location="Cincinnati")
    for j in jobs:
        assert "level " not in j.score_notes  # no seniority-fit token emitted
