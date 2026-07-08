"""Search Discovery: the `suggested_excludes` scorer lever is a bounded DOWNRANK,
never a drop, and byte-identical when unset (parity — the eng daily run is
unaffected because no legacy config carries the key).

Contrast with gate.py's `hard_no_titles`, which is a literal drop: a
suggested-exclude match must ALWAYS keep the job visible (inclusion over
precision), only sinking its score.
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


def _score(job, **kw):
    return scorer.score_job(job, keywords=KW, location="Austin, TX",
                            skill_terms=TERMS, **kw)


def test_unset_is_byte_identical():
    # None / [] / a non-matching term must all reproduce the baseline score+notes.
    job = _job("Software Engineer", desc="great role")
    base_s, base_n = _score(job)
    for val in (None, [], (), ["unrelated-term"]):
        s, n = _score(_job("Software Engineer", desc="great role"),
                      suggested_excludes=val)
        assert (s, n) == (base_s, base_n)


def test_match_downranks_but_never_drops():
    base_s, base_n = _score(_job("Software Engineer", desc="commission only role"))
    s, n = _score(_job("Software Engineer", desc="commission only role"),
                  suggested_excludes=["commission only"])
    assert s < base_s                    # sank
    assert s == base_s - scorer.SUGGESTED_EXCLUDE_PENALTY
    assert s >= 0                        # still a real score — never removed
    assert "suggested-excl" in n
    # "never drops" contract: score_job always returns a score; only gate.py drops,
    # and this lever never touches it.


def test_penalty_is_flat_and_bounded():
    # Multiple matching terms deduct the SAME flat penalty once (bounded downrank),
    # not one-per-hit — a big negative list can't crater a job out of sight.
    job_desc = "unpaid commission only contract-to-hire"
    one, _ = _score(_job("Software Engineer", desc=job_desc),
                    suggested_excludes=["commission only"])
    many, n = _score(_job("Software Engineer", desc=job_desc),
                     suggested_excludes=["commission only", "unpaid", "contract-to-hire"])
    assert one == many
    # every hit is still reported for transparency
    assert n.count(",") >= 2 and "suggested-excl" in n


def test_title_match_also_downranks():
    # Title "Software Engineer Intern" fully matches the keyword, so its base score
    # is comfortably above the penalty — the downrank is observable (not clamp-hidden).
    base_s, _ = _score(_job("Software Engineer Intern"))
    assert base_s > scorer.SUGGESTED_EXCLUDE_PENALTY   # the test is meaningful
    s, n = _score(_job("Software Engineer Intern"), suggested_excludes=["intern"])
    assert s == base_s - scorer.SUGGESTED_EXCLUDE_PENALTY
    assert "suggested-excl(intern)" in n
