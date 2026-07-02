"""S32 item 4 (review #6): Adzuna stamps the query metro onto out-of-area postings.
When the label state and a DIFFERENT state named in the body confidently disagree,
cap location credit + flag 'loc-unverified'. Never hard-drops; conservative.
"""
from models import JobResult
from match import scorer


def _job(title, loc, desc=""):
    return JobResult(title=title, company="X", location=loc, salary_min=None,
                     salary_max=None, description=desc,
                     url="http://x/" + loc, source_keyword="", created="",
                     job_id=loc + title, source_api="t")


def test_helper_contradiction():
    # label says Seattle, WA (echoes a Seattle target); body names Butte, MT.
    assert scorer._location_contradicts(
        "Seattle, King County, WA", "Position based in Butte, MT.", "Seattle, WA")


def test_helper_agreeing_body_no_contradiction():
    assert not scorer._location_contradicts(
        "Seattle, WA", "Our Seattle, WA office is downtown.", "Seattle, WA")


def test_helper_no_body_state_no_contradiction():
    assert not scorer._location_contradicts(
        "Seattle, WA", "A great remote-friendly team.", "Seattle, WA")


def test_helper_body_confirms_label_state_somewhere_trusted():
    # Conservatism: a body that names the label's state ANYWHERE (even alongside an
    # out-of-state HQ) is trusted -- protects a legit multi-office posting.
    assert not scorer._location_contradicts(
        "Cincinnati, OH", "Our HQ in Chicago, IL supports this Cincinnati, OH role.",
        "Cincinnati, OH")
    assert not scorer._location_contradicts(
        "Cincinnati, OH", "Offices in Cincinnati, OH and Austin, TX.", "Cincinnati, OH")


def test_helper_body_only_other_state_contradicts():
    assert scorer._location_contradicts(
        "Cincinnati, OH", "Our HQ in Chicago, IL. Great team.", "Cincinnati, OH")


def test_helper_remote_label_ignored():
    assert not scorer._location_contradicts(
        "Remote, WA", "Work from our Butte, MT hub.", "Seattle, WA")


def test_helper_label_not_matching_target_ignored():
    # If the label state doesn't echo the query metro, don't distrust it.
    assert not scorer._location_contradicts(
        "Denver, CO", "Role sits in Butte, MT.", "Seattle, WA")


def test_first_us_state_extraction():
    assert scorer._first_us_state("Butte, MT") == "MT"
    assert scorer._first_us_state("Position in Seattle, WA near the water") == "WA"
    assert scorer._first_us_state("no state here") is None
    assert scorer._first_us_state("Paris, ZZ") is None   # ZZ not a US state


def test_scoring_caps_location_on_contradiction():
    contradicted = _job("Mechanical Engineer", "Seattle, King County, WA",
                        desc="This position is located in Butte, MT.")
    clean = _job("Mechanical Engineer", "Seattle, King County, WA",
                 desc="Our Seattle, WA facility.")
    KW = ["mechanical engineer"]
    s_bad, n_bad = scorer.score_job(contradicted, keywords=KW, location="Seattle, WA",
                                    skill_terms=frozenset())
    s_ok, n_ok = scorer.score_job(clean, keywords=KW, location="Seattle, WA",
                                  skill_terms=frozenset())
    assert "loc-unverified" in n_bad
    assert "loc-unverified" not in n_ok
    assert s_bad < s_ok


def test_no_flag_when_no_body():
    # A row with no description body (card scrapes) is never flagged.
    j = _job("Engineer", "Seattle, WA", desc="")
    _, n = scorer.score_job(j, keywords=["engineer"], location="Seattle, WA",
                            skill_terms=frozenset())
    assert "loc-unverified" not in n
