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
    # A poor-data on-target title still reaches 100 because the missing skill/
    # salary/recency neutrals no longer dilute the present title+location weight.
    score, _ = scorer.score_job(_job("Controls Engineer"), keywords=KW, location=LOC)
    assert score == 100


def test_recency_data_lifts_confidence():
    base, nb = scorer.score_job(_job("Controls Engineer"), keywords=KW, location=LOC)
    dated, nd = scorer.score_job(_job("Controls Engineer", created="2026-06-15"),
                                 keywords=KW, location=LOC)
    assert "conf 2/5" in nb
    assert "conf 3/5" in nd  # recency now counts as real data
