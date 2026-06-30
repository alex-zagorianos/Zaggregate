from models import JobResult
from coverage.resolve import resolve

def _j(title, company, location, source):
    return JobResult(title=title, company=company, location=location, salary_min=None, salary_max=None,
                     description="", url="", source_keyword="kw", created="2026-06-22", source_api=source)

def test_identical_postings_collapse():
    jobs = [_j("Software Developer", "Acme, Inc.", "Cincinnati, OH", "adzuna"),
            _j("Software Developer", "Acme Inc",   "Cincinnati",     "themuse")]
    clusters = resolve(jobs)
    assert len(clusters) == 1
    assert clusters[0].source_ids == {"adzuna", "themuse"}

def test_distinct_jobs_separate():
    jobs = [_j("Software Developer", "Acme", "Cincinnati, OH", "adzuna"),
            _j("Mechanical Engineer", "Acme", "Cincinnati, OH", "adzuna")]
    assert len(resolve(jobs)) == 2

def test_empty_input_returns_empty():
    assert resolve([]) == []
