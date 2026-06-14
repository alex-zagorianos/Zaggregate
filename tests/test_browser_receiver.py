import pytest

from scrape.browser_receiver import _parse_salary, _safe_http_url, _to_job_result


# ── URL scheme validation (XSS guard) ────────────────────────────────────────

@pytest.mark.parametrize("url,ok", [
    ("https://example.com/job/1", True),
    ("http://example.com/job/1", True),
    ("javascript:alert(1)", False),
    ("data:text/html,<script>alert(1)</script>", False),
    ("ftp://example.com", False),
    ("", False),
])
def test_safe_http_url(url, ok):
    assert _safe_http_url(url) is ok


def test_to_job_result_rejects_javascript_url():
    job = {"title": "Engineer", "url": "javascript:fetch('http://evil')"}
    assert _to_job_result(job) is None


def test_to_job_result_rejects_non_dict():
    assert _to_job_result("not a dict") is None
    assert _to_job_result(None) is None
    assert _to_job_result(123) is None


def test_to_job_result_accepts_valid():
    job = {"title": "Controls Engineer", "url": "https://example.com/1",
           "company": "Acme", "location": "Cincinnati, OH"}
    r = _to_job_result(job)
    assert r is not None and r.title == "Controls Engineer"
    assert r.source_api == "browser_browser"


# ── salary parsing (single source of truth) ──────────────────────────────────

def test_parse_salary_annual_range():
    assert _parse_salary("$85,000 - $110,000 a year") == (85000.0, 110000.0)


def test_parse_salary_k_suffix():
    assert _parse_salary("$85K – $110K") == (85000.0, 110000.0)


def test_parse_salary_hourly_annualizes():
    lo, hi = _parse_salary("$30 - $45 / hr")
    assert lo == 30 * 2080 and hi == 45 * 2080


def test_parse_salary_hr_substring_does_not_annualize():
    """Regression: 'hr'/'hour' inside place/role names must NOT trigger x2080."""
    lo, _ = _parse_salary("$120,000 — Pittsburgh, HR Manager")
    assert lo == 120000.0  # not 120000*2080


def test_parse_salary_empty():
    assert _parse_salary("") == (None, None)
    assert _parse_salary("competitive") == (None, None)
