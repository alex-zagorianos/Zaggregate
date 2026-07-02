"""S32 item 2 (QW-2, review #2): a remote row whose label names a NON-US region
must not earn full location credit for a US-target seeker. Plain 'Remote' and a US
label are unchanged; the remote_regions_ok escape hatch restores full credit.
"""
from search.search_engine import _location_score, _target_is_us
from models import JobResult
from match import scorer, facts


# ── _location_score: the country-blind cap ─────────────────────────────────────

def test_plain_remote_still_full_marks():
    # No region token -> unchanged behavior (full remote credit).
    assert _location_score("Remote", "Austin, TX", remote_ok=True) == 3
    assert _location_score("Remote - US", "Austin, TX", remote_ok=True) == 3
    assert _location_score("Remote (US only)", "Austin, TX", remote_ok=True) == 3


def test_non_us_remote_capped_for_us_target():
    for jl in ["Remote - Czech Republic", "Remote, EMEA", "Remote (UK only)",
               "Remote - Canada", "Remote, LatAm"]:
        assert _location_score(jl, "Austin, TX", remote_ok=True) == 1, jl


def test_us_signal_in_label_suppresses_cap():
    # A role open to US AND Canada is fine for a US worker -> full marks.
    assert _location_score("Remote - US/Canada", "Austin, TX", remote_ok=True) == 3
    assert _location_score("Remote (US or Europe)", "Austin, TX", remote_ok=True) == 3


def test_escape_hatch_restores_full_credit():
    assert _location_score("Remote - Czech Republic", "Austin, TX",
                           remote_ok=True, remote_regions_ok=True) == 3


def test_non_us_target_not_capped():
    # If we can't confidently place the target in the US, don't cap (bare city).
    assert _location_score("Remote - Canada", "London", remote_ok=True) == 3


def test_remote_not_ok_still_zero():
    assert _location_score("Remote - Czech Republic", "Austin, TX", remote_ok=False) == 0


def test_target_is_us_helper():
    assert _target_is_us("Austin, TX")
    assert _target_is_us("Boise, Idaho")
    assert not _target_is_us("London")
    assert not _target_is_us("")


# ── end-to-end scoring: non-US remote sinks below a real local role ─────────────

def _job(title, loc):
    return JobResult(title=title, company="X", location=loc, salary_min=None,
                     salary_max=None, description="", url="http://x/" + loc,
                     source_keyword="", created="", job_id=loc, source_api="t")


def test_local_role_outranks_non_us_remote():
    KW = ["marketing manager"]
    local = _job("Marketing Manager", "New York, NY")
    czech = _job("Marketing Manager", "Remote - Czech Republic")
    s_local, _ = scorer.score_job(local, keywords=KW, location="New York, NY",
                                  skill_terms=frozenset())
    s_czech, _ = scorer.score_job(czech, keywords=KW, location="New York, NY",
                                  skill_terms=frozenset())
    assert s_local > s_czech


# ── facts: a non-US remote LABEL surfaces a restriction for the AI gate ─────────

def test_label_restriction_detected():
    assert facts._detect_restriction_label("Remote - Czech Republic") == "Non-US location required"
    assert facts._detect_restriction_label("Remote, EMEA") == "Non-US location required"
    assert facts._detect_restriction_label("Remote") is None
    assert facts._detect_restriction_label("Remote - US") is None
    assert facts._detect_restriction_label("Austin, TX") is None


def test_extract_facts_surfaces_label_restriction():
    j = _job("Engineer", "Remote - Czechia")
    f = facts.extract_facts(j)
    assert f["restriction"] == "Non-US location required"
    # escape hatch: opted-in user keeps it None
    f2 = facts.extract_facts(j, remote_regions_ok=True)
    assert f2["restriction"] is None


def test_extract_facts_us_remote_unchanged():
    # A plain/US remote label must not gain a restriction (byte-identical).
    assert facts.extract_facts(_job("Engineer", "Remote"))["restriction"] is None
    assert facts.extract_facts(_job("Engineer", "Remote, US"))["restriction"] is None
