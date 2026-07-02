"""S32 item 5 (review #4): opt-in title-family disambiguation. When a profile sets
title_context_required, a whole-query title match on an ambiguous head term
("engagement manager") keeps full credit only if a domain context token co-occurs.
Default (no list) is byte-identical -- the real fix stays the BYO-AI Fit pass.
"""
from models import JobResult
from match import scorer


def _job(title, desc=""):
    return JobResult(title=title, company="X", location="Chicago, IL", salary_min=None,
                     salary_max=None, description=desc,
                     url="http://x/" + title.replace(" ", ""), source_keyword="",
                     created="", job_id=title, source_api="t")


KW = ["engagement manager"]
CTX = ["consulting", "strategy", "advisory"]


def test_unset_context_is_byte_identical():
    # No title_context_required -> every "engagement manager" family title keeps the
    # same title-100% score (the pre-S32 behavior we preserve when un-opted-in).
    titles = ["Engagement Manager - Management Consulting", "AWS ProServe Engagement Manager",
              "Community Engagement Manager", "Customer Success Engagement Manager"]
    scores = {t: scorer.score_job(_job(t), keywords=KW, location="Chicago, IL",
                                  skill_terms=frozenset())[0] for t in titles}
    assert len(set(scores.values())) == 1  # all identical (the documented defect)


def test_context_cap_demotes_off_domain():
    real = _job("Engagement Manager", desc="A management consulting strategy role.")
    aws = _job("AWS ProServe Engagement Manager", desc="Cloud delivery for AWS customers.")
    s_real, n_real = scorer.score_job(real, keywords=KW, location="Chicago, IL",
                                      skill_terms=frozenset(), title_context_required=CTX)
    s_aws, n_aws = scorer.score_job(aws, keywords=KW, location="Chicago, IL",
                                    skill_terms=frozenset(), title_context_required=CTX)
    assert "title-context-cap" in n_aws
    assert "title-context-cap" not in n_real   # has 'consulting'/'strategy' context
    assert s_real > s_aws


def test_context_token_in_title_counts():
    # Context can co-occur in the TITLE, not only the description.
    j = _job("Strategy Engagement Manager")
    _, n = scorer.score_job(j, keywords=KW, location="Chicago, IL",
                            skill_terms=frozenset(), title_context_required=CTX)
    assert "title-context-cap" not in n


def test_score_jobs_threads_context_to_all_jobs():
    jobs = [_job("AWS ProServe Engagement Manager"),
            _job("Community Engagement Manager"),
            _job("Engagement Manager", desc="management consulting advisory")]
    scorer.score_jobs(jobs, keywords=KW, location="Chicago, IL",
                      title_context_required=CTX)
    caps = {j.title: ("title-context-cap" in j.score_notes) for j in jobs}
    assert caps["AWS ProServe Engagement Manager"] is True
    assert caps["Community Engagement Manager"] is True
    assert caps["Engagement Manager"] is False


def test_partial_title_match_not_capped():
    # The cap only applies to a WHOLE-query match (t>=1.0); a partial-overlap title
    # is left to the existing title-miss machinery.
    j = _job("Engagement Coordinator")  # partial, not a full "engagement manager"
    _, n = scorer.score_job(j, keywords=KW, location="Chicago, IL",
                            skill_terms=frozenset(), title_context_required=CTX)
    assert "title-context-cap" not in n
