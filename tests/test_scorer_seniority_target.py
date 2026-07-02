"""S32 item 1 (P0-3): a keyless user's local Score must stop tying an over-leveled
role (Sr./II·III/IV/8+ YOE) with a plain entry title. The nudge is GATED on the
config's seniority_target; a profile that sets none scores byte-identical.

Regression-critical: proves ungated profiles are unchanged AND the exec/IC keyword
seniority feature (test_seniority_fit) is untouched.
"""
from models import JobResult
from match import scorer


def _job(title, desc="", loc="Austin, TX"):
    return JobResult(title=title, company="X", location=loc, salary_min=None,
                     salary_max=None, description=desc,
                     url="http://x/" + title.replace(" ", ""), source_keyword="",
                     created="", job_id=title, source_api="t")


KW = ["software engineer"]
TERMS = frozenset()  # hermetic: no ambient experience.md skills


# ── the nudge only fires when seniority_target is set (byte-identity when unset) ─

def test_unset_target_is_byte_identical():
    # No seniority_target -> the S32 nudge never engages; score + notes unchanged
    # from the pre-S32 contract for every title.
    for t in ["Software Engineer", "Sr. Software Engineer", "Software Engineer III",
              "Software Engineer IV", "Staff Software Engineer"]:
        s, n = scorer.score_job(_job(t), keywords=KW, location="Austin, TX",
                                skill_terms=TERMS)
        assert "over-target" not in n
        # An unset target must give an over-leveled title the SAME score as a plain
        # one (that IS the pre-fix behavior we are preserving for ungated profiles).
        s_plain, _ = scorer.score_job(_job("Software Engineer"), keywords=KW,
                                      location="Austin, TX", skill_terms=TERMS)
        assert s == s_plain


# ── the nudge down-ranks explicit over-level titles for an entry seeker ──────────

def test_entry_target_downranks_senior_family():
    plain, _ = scorer.score_job(_job("Software Engineer"), keywords=KW,
                                location="Austin, TX", skill_terms=TERMS,
                                seniority_target="entry", years_cap=3)
    for t in ["Sr. Software Engineer", "Software Engineer III", "Software Engineer IV",
              "Senior Software Engineer", "Staff Software Engineer"]:
        s, n = scorer.score_job(_job(t), keywords=KW, location="Austin, TX",
                                skill_terms=TERMS, seniority_target="entry", years_cap=3)
        assert "over-target" in n
        assert s < plain, f"{t!r} ({s}) should sink below a plain entry title ({plain})"


def test_plain_and_level_two_untouched_for_entry():
    # The unmarked 'mid' default and an "Engineer II" (mid) must NOT be nudged: only
    # an explicit over-level marker down-ranks, else an entry seeker would penalize
    # every plain title (all read as 'mid').
    base, _ = scorer.score_job(_job("Software Engineer"), keywords=KW,
                               location="Austin, TX", skill_terms=TERMS)
    for t in ["Software Engineer", "Software Engineer II"]:
        s, n = scorer.score_job(_job(t), keywords=KW, location="Austin, TX",
                                skill_terms=TERMS, seniority_target="entry", years_cap=3)
        assert "over-target" not in n
        assert s == base


def test_years_over_cap_downranks_even_without_title_marker():
    # An explicit "8+ years of experience" in the body over a years_cap=3 nudges
    # even when the title carries no seniority word.
    plain, _ = scorer.score_job(_job("Software Engineer"), keywords=KW,
                                location="Austin, TX", skill_terms=TERMS,
                                seniority_target="entry", years_cap=3)
    s, n = scorer.score_job(
        _job("Software Engineer", desc="Requires 8+ years of experience."),
        keywords=KW, location="Austin, TX", skill_terms=TERMS,
        seniority_target="entry", years_cap=3)
    assert "over-target" in n
    assert s < plain


def test_at_or_below_target_untouched():
    # A senior seeker's senior/lead roles are AT target -> no nudge.
    for t in ["Senior Software Engineer", "Software Engineer III", "Staff Software Engineer"]:
        s, n = scorer.score_job(_job(t), keywords=KW, location="Austin, TX",
                                skill_terms=TERMS, seniority_target="senior", years_cap=12)
        assert "over-target" not in n


def test_nudge_bounded():
    # The total S32 nudge never exceeds -12 (title marker + years-over-cap combined).
    s_plain, _ = scorer.score_job(_job("Software Engineer"), keywords=KW,
                                  location="Austin, TX", skill_terms=TERMS,
                                  seniority_target="entry", years_cap=3)
    s, _ = scorer.score_job(
        _job("Director of Engineering", desc="20+ years of experience required."),
        keywords=KW, location="Austin, TX", skill_terms=TERMS,
        seniority_target="entry", years_cap=3)
    # director + years-over-cap would be -12-8 unbounded; the helper caps at -12.
    # (Other penalties like title-miss apply independently; here we just assert the
    # over-target token reports a bounded value.)
    _, n = scorer.score_job(
        _job("Director of Engineering", desc="20+ years of experience required."),
        keywords=KW, location="Austin, TX", skill_terms=TERMS,
        seniority_target="entry", years_cap=3)
    tok = [x.strip() for x in n.split("|") if "over-target" in x][0]
    val = int(tok.split()[-1])
    assert val == -12


def test_desc_senior_mention_does_not_nudge():
    # A plain title whose BODY incidentally mentions "senior engineers" must NOT be
    # down-nudged (seniority for the nudge is read from the TITLE only).
    base, _ = scorer.score_job(_job("Software Engineer"), keywords=KW,
                               location="Austin, TX", skill_terms=TERMS)
    j = _job("Software Engineer", desc="Join our team of senior engineers.")
    s, n = scorer.score_job(j, keywords=KW, location="Austin, TX", skill_terms=TERMS,
                            seniority_target="entry", years_cap=3)
    assert "over-target" not in n
    assert s == base


def test_score_jobs_threads_target():
    jobs = [_job("Software Engineer"), _job("Sr. Software Engineer")]
    scorer.score_jobs(jobs, keywords=KW, location="Austin, TX",
                      seniority_target="entry", years_cap=3)
    by = {j.title: j.score for j in jobs}
    assert by["Software Engineer"] > by["Sr. Software Engineer"]


def test_score_jobs_no_target_unchanged():
    # Without a target, score_jobs must not emit the token for any title.
    jobs = [_job("Software Engineer"), _job("Sr. Software Engineer")]
    scorer.score_jobs(jobs, keywords=KW, location="Austin, TX")
    for j in jobs:
        assert "over-target" not in j.score_notes
