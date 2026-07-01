"""Tests for coverage/reach.py — job-level reach certification from a run's raw
multi-source results."""
import coverage.reach as reach
from models import JobResult


def test_badge_line_none_and_uncertifiable_and_certified():
    # No snapshot -> blank badge (GUI shows nothing).
    assert reach.badge_line(None) == ""
    assert reach.badge_line({}) == ""
    # Not certifiable (disjoint sources) -> honest, no bare percentage.
    unc = {"n_distinct": 917, "n_families": 8, "coverage_pct": None,
           "coverage_ci": None, "certifiable": False}
    t = reach.badge_line(unc)
    assert "not yet certifiable" in t and "917 distinct" in t and "%" not in t
    # Certifiable -> qualified percentage with the CI band.
    cert = {"n_distinct": 300, "n_families": 3, "coverage_pct": 62.0,
            "coverage_ci": [55.0, 71.0], "certifiable": True}
    t2 = reach.badge_line(cert)
    assert t2.startswith("Reach ~62%") and "(55–71%)" in t2 and "3 src families" in t2


def mk(title, company, source, loc="Cincinnati, OH", url=""):
    return JobResult(title=title, company=company, location=loc,
                     salary_min=None, salary_max=None, description="",
                     url=url, source_keyword=title, created="",
                     job_id=f"{source}_{company}_{title}", source_api=source)


def _two_family_run():
    """40 adzuna-only + 40 usajobs-only + 20 in BOTH (overlap) -> 100 distinct."""
    jobs = []
    for i in range(40):
        jobs.append(mk("controls engineer", f"AceCo{i}", "adzuna"))
    for i in range(40):
        jobs.append(mk("controls engineer", f"BeeCo{i}", "usajobs"))
    for i in range(20):                       # same posting seen by both families
        jobs.append(mk("controls engineer", f"OverlapCo{i}", "adzuna"))
        jobs.append(mk("controls engineer", f"OverlapCo{i}", "usajobs"))
    return jobs


def test_two_families_certifiable_with_overlap():
    est = reach.estimate_reach(_two_family_run(), area="Cincinnati, OH", industry="controls")
    assert est.n_raw == 120 and est.n_distinct == 100
    assert est.n_families == 2 and set(est.families) == {"adzuna", "usajobs"}
    assert est.method == "chapman"
    assert est.certifiable is True
    assert est.n_hat is not None and est.n_hat >= est.n_distinct
    assert 0 < est.coverage_pct <= 100
    assert est.coverage_ci is not None and est.coverage_ci[0] <= est.coverage_ci[1]
    assert est.unseen is not None and est.unseen >= 0
    # Chapman: N̂ = (n1+1)(n2+1)/(m+1)-1 with n1=n2=60, m=20 -> ~176 -> ~57% cov.
    assert 45 <= est.coverage_pct <= 70


def test_single_family_cannot_certify():
    jobs = [mk("nurse", f"Hosp{i}", "adzuna") for i in range(30)]
    est = reach.estimate_reach(jobs, area="Ohio", industry="nursing")
    assert est.n_families == 1
    assert est.certifiable is False
    assert est.coverage_pct is None
    assert "need >=2 independent source families" in est.message
    # Good-Turing completeness still reported (assumption-light, no overlap needed).
    assert est.completeness is not None


def test_correlated_sources_collapse_to_one_family():
    # A posting found by BOTH serpapi and jsearch is ONE Google-Jobs capture, so
    # a run split only across those two collapses to a single family -> not certifiable.
    jobs = []
    for i in range(20):
        jobs.append(mk("data analyst", f"Co{i}", "serpapi"))
        jobs.append(mk("data analyst", f"Co{i}", "jsearch"))
    est = reach.estimate_reach(jobs, industry="analytics")
    assert est.families == ["google_jobs"]
    assert est.n_families == 1 and est.certifiable is False


def test_three_families_uses_loglinear():
    jobs = _two_family_run()
    for i in range(30):                        # a third independent family
        jobs.append(mk("controls engineer", f"CeeCo{i}", "themuse"))
    for i in range(10):                        # some 3-way overlap
        jobs.append(mk("controls engineer", f"OverlapCo{i}", "themuse"))
    est = reach.estimate_reach(jobs, industry="controls")
    assert est.n_families == 3
    assert est.method == "loglinear+bootstrap"
    assert est.n_hat_ci is not None and est.n_hat_ci[0] <= est.n_hat_ci[1]


def test_empty_run():
    est = reach.estimate_reach([], area="X")
    assert est.n_raw == 0 and est.n_distinct == 0
    assert est.certifiable is False
    assert est.summary_line()  # doesn't raise


def test_three_disjoint_families_cannot_certify():
    # 3 independent families with ZERO cross-source overlap: loglinear degenerates
    # to n_distinct, which used to be reported as a false 100%. Must NOT certify.
    jobs = []
    for i in range(50):
        jobs.append(mk("controls engineer", f"Aco{i}", "adzuna"))
    for i in range(50):
        jobs.append(mk("controls engineer", f"Bco{i}", "usajobs"))
    for i in range(50):
        jobs.append(mk("controls engineer", f"Cco{i}", "themuse"))
    est = reach.estimate_reach(jobs, industry="controls")
    assert est.n_families == 3
    assert est.certifiable is False
    assert est.coverage_pct is None
    assert "no cross-source overlap" in est.message
    assert est.summary_line()  # doesn't raise


def test_small_overlap_chapman_ci_has_no_none():
    # n1=n2 large with a single recapture (m=1) gives a Chapman Wald CI whose lower
    # bound on N is NEGATIVE -> the coverage CI upper bound must clamp to 100, never
    # leave a None (which crashed summary_line's %-formatting).
    jobs = []
    for i in range(199):
        jobs.append(mk("nurse", f"Aco{i}", "adzuna"))
    for i in range(199):
        jobs.append(mk("nurse", f"Bco{i}", "usajobs"))
    jobs.append(mk("nurse", "Shared", "adzuna"))
    jobs.append(mk("nurse", "Shared", "usajobs"))   # the single overlap (m=1)
    est = reach.estimate_reach(jobs, industry="nursing")
    assert est.method == "chapman" and est.certifiable is True
    assert est.coverage_ci is not None
    assert est.coverage_ci[0] is not None and est.coverage_ci[1] is not None
    assert est.summary_line()  # must not raise TypeError on a None CI bound


def test_summary_line_certifiable_shape():
    est = reach.estimate_reach(_two_family_run(), area="Cincinnati", industry="controls")
    line = est.summary_line()
    assert "seeing ~" in line and "95% CI" in line and "unseen" in line


def test_persist_and_load_roundtrip(tmp_path, monkeypatch):
    import config
    monkeypatch.setattr(config, "USER_DATA_DIR", tmp_path)
    est = reach.estimate_reach(_two_family_run(), area="Cincinnati", industry="controls")
    p = reach.persist_reach(est, project="controls-test")
    assert p.exists()
    loaded = reach.load_latest("controls-test")
    assert loaded is not None
    assert loaded["project"] == "controls-test"
    assert loaded["n_distinct"] == est.n_distinct
    assert reach.load_latest("does-not-exist") is None
