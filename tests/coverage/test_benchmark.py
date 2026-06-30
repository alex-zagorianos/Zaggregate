from models import JobResult
from coverage.benchmark import run_benchmark

def _j(title, company, source):
    return JobResult(title=title, company=company, location="Cincinnati, OH", salary_min=None, salary_max=None,
                     description="", url="", source_keyword="kw", created="2026-06-22", source_api=source)

def _two_source_jobs():
    # one cross-source dupe + singles -> 2 sources present
    return [_j("Software Developer", "Acme", "adzuna"), _j("Software Developer", "Acme", "themuse"),
            _j("Mechanical Engineer", "Beta", "adzuna"), _j("Data Scientist", "Gamma", "themuse")]

def test_two_source_fixture_populates_cr(tmp_path):
    r = run_benchmark(_two_source_jobs(), "Cincinnati, OH", ["15-1252.00"], out_dir=tmp_path)
    assert r.paths_used["cr"] == "chapman"
    assert r.cov_cr is not None

def test_composite_renormalizes_missing_legs(tmp_path):
    r = run_benchmark(_two_source_jobs(), "Cincinnati, OH", [], out_dir=tmp_path)
    assert r.cov_proxy_weighted is None  # no provider
    assert 0 <= r.composite_score <= 100

def test_persists_report(tmp_path):
    run_benchmark(_two_source_jobs(), "Cincinnati, OH", [], out_dir=tmp_path)
    assert (tmp_path / "runs.jsonl").exists()
