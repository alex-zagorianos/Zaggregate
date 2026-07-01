"""C1: match.ghost consumes freshness.repost_info to bump repost/evergreen rows.

Pure, no I/O. The signal is abstain-safe: default None or a job absent from the
map contributes nothing (today's behavior exactly)."""
from match import ghost


def _job(job_key="jk1", title="Data Analyst"):
    # A dict is one of ghost_score's accepted shapes (inbox row). No `created`
    # (age abstains) and salary present (no missing-salary bump) so the ONLY
    # signal under test is repost/evergreen - nothing else muddies the score.
    return {"job_key": job_key, "title": title, "salary_text": "$100k",
            "salary_min": 100000, "created": ""}


def test_default_none_is_abstain_unchanged():
    # No repost_info -> identical to the historical behavior (no repost reason).
    r = ghost.ghost_score(_job())
    assert "reposted" not in r["reasons"]
    assert "evergreen listing" not in r["reasons"]


def test_job_absent_from_map_abstains():
    info = {"other": {"first_seen": "", "repost": True, "evergreen": False}}
    r = ghost.ghost_score(_job(job_key="jk1"), repost_info=info)
    assert "reposted" not in r["reasons"]


def test_repost_bumps_with_reason():
    info = {"jk1": {"first_seen": "", "repost": True, "evergreen": False}}
    base = ghost.ghost_score(_job())["score"]
    r = ghost.ghost_score(_job(), repost_info=info)
    assert "reposted" in r["reasons"]
    assert r["score"] > base


def test_evergreen_bumps_with_reason():
    info = {"jk1": {"first_seen": "", "repost": False, "evergreen": True}}
    base = ghost.ghost_score(_job())["score"]
    r = ghost.ghost_score(_job(), repost_info=info)
    assert "evergreen listing" in r["reasons"]
    assert r["score"] > base
    assert r["level"] == "stale"   # evergreen alone clears the stale line


def test_both_flags_bump_more():
    info = {"jk1": {"first_seen": "", "repost": True, "evergreen": True}}
    r = ghost.ghost_score(_job(), repost_info=info)
    assert "reposted" in r["reasons"] and "evergreen listing" in r["reasons"]
    assert r["score"] == 100 or r["score"] >= 60


def test_repost_signal_fires_even_with_no_other_signal():
    # A row with NO date and salary present would otherwise be 'unknown'; a repost
    # flag alone must produce a real (non-unknown) result.
    row = {"job_key": "jk1", "title": "Analyst", "salary_min": 90000,
           "salary_text": "$90k", "created": ""}
    info = {"jk1": {"first_seen": "", "repost": True, "evergreen": False}}
    r = ghost.ghost_score(row, repost_info=info)
    assert r["level"] != "unknown"
    assert "reposted" in r["reasons"]


def test_jobresult_attr_shape_supported():
    from models import JobResult
    j = JobResult(title="X", company="Y", location="", salary_min=100000,
                  salary_max=120000, description="", url="", source_keyword="",
                  created="2026-06-30", source_api="t")
    info = {j.job_key: {"first_seen": "", "repost": True, "evergreen": False}}
    r = ghost.ghost_score(j, repost_info=info)
    assert "reposted" in r["reasons"]
