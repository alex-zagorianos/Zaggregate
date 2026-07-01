"""URL-less dedup must not merge the same title at the same company in two
DIFFERENT locations (finding #14), but must still collapse cross-source remote
variants (Remote / Remote, US / Anywhere)."""
from models import JobResult
from search.search_engine import SearchEngine


def _job(title, company, location, url=""):
    return JobResult(title=title, company=company, location=location, salary_min=None,
                     salary_max=None, description="", url=url, source_keyword="",
                     created="", job_id=title + location, source_api="t")


def test_urlless_distinct_cities_not_merged():
    jobs = [
        _job("Director of Clinical Informatics", "Acme Health", "Cincinnati, OH"),
        _job("Director of Clinical Informatics", "Acme Health", "Remote"),
    ]
    out = SearchEngine([])._deduplicate(jobs)
    assert len(out) == 2, "distinct-city URL-less postings were over-merged"


def test_urlless_remote_variants_still_merge():
    jobs = [
        _job("Data Analyst", "Acme", "Remote"),
        _job("Data Analyst", "Acme", "Remote, US"),
        _job("Data Analyst", "Acme", "Anywhere"),
    ]
    out = SearchEngine([])._deduplicate(jobs)
    assert len(out) == 1, "cross-source remote variants should still dedup to one"


def test_url_dedup_unaffected():
    jobs = [
        _job("X", "Y", "Cincinnati", url="http://ats/job/1"),
        _job("X", "Y", "Remote", url="http://ats/job/1"),  # same URL = same job
    ]
    out = SearchEngine([])._deduplicate(jobs)
    assert len(out) == 1
