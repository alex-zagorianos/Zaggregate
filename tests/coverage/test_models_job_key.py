from models import JobResult
from coverage import entity

def _job():
    return JobResult(title="Software Developer", company="Acme, Inc.", location="Cincinnati, OH",
                     salary_min=None, salary_max=None, description="", url="", source_keyword="kw",
                     created="2026-06-22", source_api="adzuna")

def test_job_key_matches_entity():
    j = _job()
    assert j.job_key == entity.job_key_for(j)

def test_job_key_is_cached():
    j = _job()
    assert j.job_key is j.job_key  # cached_property memoizes the same object
