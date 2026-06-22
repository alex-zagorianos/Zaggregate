from models import JobResult
import search.freshness as F

def _j(title, company="Acme", location="Cincinnati, OH"):
    return JobResult(title=title, company=company, location=location, salary_min=None, salary_max=None,
                     description="", url="", source_keyword="kw", created="2026-06-22", source_api="adzuna")

def test_new_since_last_filters_seen():
    a, b = _j("Software Developer"), _j("Mechanical Engineer")
    prev = {a.job_key}
    out = F.new_since_last([a, b], "adzuna", prev)
    assert out == [b]

def test_persist_roundtrip(tmp_path):
    a = _j("Software Developer")
    F.save_keys("adzuna", {a.job_key}, base_dir=tmp_path)
    assert F.load_prev_keys("adzuna", base_dir=tmp_path) == {a.job_key}

def test_load_missing_returns_empty(tmp_path):
    assert F.load_prev_keys("never_run", base_dir=tmp_path) == set()
