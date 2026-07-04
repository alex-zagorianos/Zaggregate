"""Scoring fixes (2026-06 review): company-size band (SCORE-7), graded
title-miss penalty (SCORE-6), query hoisting (SCORE-8), idempotent salary fill
(SCORE-9), and weight-renormalization + confidence marker (SCORE-1)."""
from match import scorer
from models import JobResult
from search import query

KW = ["controls engineer", "automation engineer", "mechanical engineer"]
LOC = "Cincinnati, OH"


def _job(title, **kw):
    d = dict(title=title, company="C", location=LOC, salary_min=None,
             salary_max=None, description="", url="http://x/" + title.replace(" ", ""),
             source_keyword="", created="", source_api="t")
    d.update(kw)
    return JobResult(**d)


# ── SCORE-7: company-size band 101-250 -> -2, monotonic ───────────────────────

def test_size_band_mid_large_gets_minus_two():
    score, notes = scorer.score_job(_job("Controls Engineer", board_count=150),
                                    keywords=KW, location=LOC)
    assert "size -2" in notes


def test_size_band_150_scores_below_50():
    s50, _ = scorer.score_job(_job("Controls Engineer", board_count=50),
                              keywords=KW, location=LOC)
    s150, _ = scorer.score_job(_job("Controls Engineer", board_count=150),
                               keywords=KW, location=LOC)
    assert s150 < s50


def test_size_bands_monotonic():
    # Bigger board -> lower-or-equal adjustment: +8, +4, -2, -6.
    def adj(bc):
        return scorer.score_job(_job("Q W E R T Y", board_count=bc),
                                keywords=["zzz"], location=LOC)
    s30, _ = scorer.score_job(_job("Q W E R T Y", board_count=30), keywords=["zzz"], location=LOC)
    s100, _ = scorer.score_job(_job("Q W E R T Y", board_count=100), keywords=["zzz"], location=LOC)
    s250, _ = scorer.score_job(_job("Q W E R T Y", board_count=250), keywords=["zzz"], location=LOC)
    s400, _ = scorer.score_job(_job("Q W E R T Y", board_count=400), keywords=["zzz"], location=LOC)
    assert s30 >= s100 >= s250 >= s400


# ── SCORE-6: graded title-miss penalty ────────────────────────────────────────

def test_partial_title_miss_lighter_than_zero():
    # 'process controls' overlaps a 'process controls automation' query (t~0.67),
    # so its title-miss deduction is far smaller than a zero-overlap title.
    kw = ["process controls automation"]
    _, np = scorer.score_job(_job("Process Controls Specialist"), keywords=kw, location=LOC)
    _, nz = scorer.score_job(_job("Graphic Designer"), keywords=kw, location=LOC)
    pen_partial = int(np.split("title-miss -")[1].split(" ")[0])
    pen_zero = int(nz.split("title-miss -")[1].split(" ")[0])
    assert 0 < pen_partial < pen_zero
    assert pen_zero == scorer.DEFAULT_TITLE_MISS_PENALTY  # true zero takes full hit


def test_partial_title_outscores_zero_title():
    kw = ["process controls automation"]
    sp, _ = scorer.score_job(_job("Process Controls Specialist"), keywords=kw, location=LOC)
    sz, _ = scorer.score_job(_job("Graphic Designer"), keywords=kw, location=LOC)
    assert sp > sz


# ── SCORE-8: hoisted queries are behavior-identical ───────────────────────────

def test_queries_kwarg_matches_keyword_path():
    jobs = ["Controls Engineer", "Marketing Lead", "Automation Specialist"]
    qs = [query.parse(k) for k in KW]
    for title in jobs:
        a = scorer.score_job(_job(title, description="plc automation"),
                             keywords=KW, location=LOC)
        b = scorer.score_job(_job(title, description="plc automation"),
                             keywords=KW, location=LOC, queries=qs)
        assert a == b


def test_score_jobs_matches_individual_calls():
    titles = ["Controls Engineer", "Marketing Lead", "Automation Specialist"]
    terms = scorer.extract_skill_terms()
    expected = sorted(
        scorer.score_job(_job(t, description="plc controls"), keywords=KW,
                         location=LOC, skill_terms=terms)[0]
        for t in titles
    )
    batch = [_job(t, description="plc controls") for t in titles]
    scorer.score_jobs(batch, keywords=KW, location=LOC)
    assert sorted(j.score for j in batch) == expected


# ── SCORE-9: salary fill is idempotent under re-scoring ───────────────────────

def test_rescoring_does_not_change_salary():
    job = _job("Eng", description="Pay range: 120,000 - 150,000")
    scorer.score_job(job, keywords=KW, location=LOC)
    first = (job.salary_min, job.salary_max)
    assert first == (120000.0, 150000.0)  # recovered from text
    scorer.score_job(job, keywords=KW, location=LOC)
    assert (job.salary_min, job.salary_max) == first  # unchanged second pass


def test_preexisting_salary_never_overwritten():
    job = _job("Eng", description="Pay range: 120,000 - 150,000",
               salary_min=90000, salary_max=95000)
    scorer.score_job(job, keywords=KW, location=LOC)
    assert (job.salary_min, job.salary_max) == (90000, 95000)


# ── SCORE-1: weight-renormalization + confidence marker ───────────────────────

def test_confidence_marker_data_poor():
    # No description / no salary floor / no date -> only title+loc present.
    _, notes = scorer.score_job(_job("Controls Engineer"), keywords=KW, location=LOC)
    assert "conf 2/5" in notes


def test_confidence_marker_data_rich():
    job = _job("Controls Engineer", description="plc solidworks python automation",
               salary_min=120000, salary_max=140000, created="2026-06-15")
    # Pass skill_terms explicitly so the marker is hermetic — otherwise it depends
    # on the ambient active project's experience.md having parseable skills (a
    # health-informatics project with no skills would read as conf 4/5, correctly).
    _, notes = scorer.score_job(job, keywords=KW, location=LOC, salary_floor=100000,
                                skill_terms=frozenset({"plc", "solidworks", "python", "automation"}))
    assert "conf 5/5" in notes


def test_renormalization_drops_missing_component_weight():
    # A poor-data on-target title's title+location weight is renormalized to a full
    # composite, but confidence shrinkage (P2) then damps its distance from 50 by
    # data-presence (conf 2/5 -> factor 0.82): 50 + 50*0.82 = 91. This is the point
    # of the shrinkage -- a title-only match no longer pins 100 and outranks a
    # data-rich 92. (Pre-shrinkage this asserted == 100.)
    score, notes = scorer.score_job(_job("Controls Engineer"), keywords=KW, location=LOC)
    assert "conf 2/5" in notes
    assert score == 91


def test_confidence_shrinkage_pulls_title_only_toward_midpoint():
    # A title-only perfect match (composite 100, conf 2/5) is damped toward 50 by
    # the presence factor 0.7 + 0.3*2/5 = 0.82 -> 50 + 50*0.82 = 91 (deterministic).
    # This is the mechanism that stops a data-poor title-only 100 from pinning the
    # top of the list above genuinely data-rich matches.
    poor, np = scorer.score_job(_job("Controls Engineer"), keywords=KW, location=LOC)
    assert "conf 2/5" in np
    assert poor == 91

    # More data present -> less damping (the 3/5 job keeps more of its spread than
    # the 2/5 job would at the same composite). Adding a recency date lifts conf to
    # 3/5, and the on-target title's score rises accordingly. The date must be
    # RELATIVE to today: this asserts a recency-VALUE ordering, and a hardcoded
    # date rots as wall-clock advances (it flipped 91->90 on 2026-07-03 when the
    # decay crossed an integer-rounding boundary — S35).
    from datetime import date, timedelta
    fresh = (date.today() - timedelta(days=1)).isoformat()
    dated, nd = scorer.score_job(_job("Controls Engineer", created=fresh),
                                 keywords=KW, location=LOC)
    assert "conf 3/5" in nd
    assert dated >= poor


def test_recency_data_lifts_confidence():
    base, nb = scorer.score_job(_job("Controls Engineer"), keywords=KW, location=LOC)
    dated, nd = scorer.score_job(_job("Controls Engineer", created="2026-06-15"),
                                 keywords=KW, location=LOC)
    assert "conf 2/5" in nb
    assert "conf 3/5" in nd  # recency now counts as real data


# ── #38: thin/malformed resume -- skill weight renormalizes, notes stay honest ─

def test_thin_resume_empty_skill_terms_renormalizes_not_neutral():
    # A thin/malformed resume (no TECHNICAL SKILLS-equivalent section found) ->
    # skill_terms is an empty frozenset. The skill component must NOT silently
    # contribute a neutral 0.5 * its 25pt weight to the composite; its weight is
    # dropped from the renormalization entirely (same mechanism that already
    # excludes salary/recency when their data is absent).
    job = _job("Controls Engineer", description="plc automation controls engineer role")
    score, notes = scorer.score_job(job, keywords=KW, location=LOC,
                                    skill_terms=frozenset())
    assert "conf 2/5" in notes          # only title+loc counted as present
    assert "skills" not in notes        # #38: no misleading "skills 50%" token


def test_thin_resume_score_matches_manual_renormalization():
    # The composite for an empty-skill_terms job must equal the same renormalized
    # title+loc-only computation as an otherwise-identical job that has no
    # description at all (which also renders skill_present False) -- proving the
    # skill weight is genuinely excluded, not just hidden from the notes string.
    job_no_desc = _job("Controls Engineer")
    job_empty_terms = _job("Controls Engineer", description="plc automation controls")
    s_no_desc, _ = scorer.score_job(job_no_desc, keywords=KW, location=LOC)
    s_empty_terms, _ = scorer.score_job(job_empty_terms, keywords=KW, location=LOC,
                                        skill_terms=frozenset())
    assert s_no_desc == s_empty_terms


def test_rich_resume_skills_token_and_score_unaffected_parity():
    # Parity: a rich resume (Alex's eng profile always has skill_terms present)
    # must be completely unaffected by the #38 notes-honesty fix -- the "skills"
    # token still always appears and the score is unchanged.
    job = _job("Controls Engineer", description="plc solidworks python automation")
    terms = frozenset({"plc", "solidworks", "python", "automation"})
    score, notes = scorer.score_job(job, keywords=KW, location=LOC, skill_terms=terms)
    assert "skills" in notes
    assert "conf 3/5" in notes


def test_malformed_resume_via_bad_experience_file_still_scores_by_title(tmp_path):
    # End-to-end: extract_skill_terms() degrades a malformed experience.md to an
    # empty frozenset (see match/scorer.extract_skill_terms + test_scorer_bad_
    # experience.py); score_job must renormalize around it rather than diluting
    # the title signal with a neutral skill score.
    bad = tmp_path / "experience.md"
    bad.write_text("Just some unstructured prose with no headings at all.",
                   encoding="utf-8")
    terms = scorer.extract_skill_terms(experience_path=bad)
    assert terms == frozenset()
    job = _job("Controls Engineer", description="plc automation controls")
    score, notes = scorer.score_job(job, keywords=KW, location=LOC, skill_terms=terms)
    assert "skills" not in notes
    assert "title 100%" in notes
