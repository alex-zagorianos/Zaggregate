from models import JobResult
from search.search_engine import SearchEngine

def _j(title, company, location, url, source):
    return JobResult(title=title, company=company, location=location, salary_min=None, salary_max=None,
                     description="", url=url, source_keyword="kw", created="2026-06-22", source_api=source)

def _dedup(jobs):
    return SearchEngine(clients=[])._deduplicate(jobs)

def test_url_fast_path_still_dedupes():
    jobs = [_j("Eng", "Acme", "Cincinnati, OH", "https://x.co/1?utm_source=a", "s1"),
            _j("Eng", "Acme", "Cincinnati, OH", "https://x.co/1?utm_source=b", "s2")]
    assert len(_dedup(jobs)) == 1  # tracking-variant URLs collapse (characterization parity)

def test_cross_source_dupe_collapsed_by_job_key():
    jobs = [_j("Software Developer", "Acme, Inc.", "Cincinnati, OH", "", "adzuna"),
            _j("Software Developer", "Acme Inc",   "Cincinnati",     "", "themuse")]
    assert len(_dedup(jobs)) == 1  # no URLs, different formatting -> job_key collapses

def test_distinct_jobs_survive():
    jobs = [_j("Software Developer", "Acme", "Cincinnati, OH", "", "adzuna"),
            _j("Mechanical Engineer", "Acme", "Cincinnati, OH", "", "adzuna")]
    assert len(_dedup(jobs)) == 2
