import pytest

from scrape.browser_receiver import (
    _origin_allowed,
    _parse_salary,
    _safe_http_url,
    _to_job_result,
    app,
)


@pytest.fixture
def client():
    app.config["TESTING"] = True
    return app.test_client()


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


# ── EXT-4: prefer ranged/period pattern over first-two-dollar heuristic ───────

def test_parse_salary_promo_dollar_before_range():
    """A promo/bonus $ ahead of the real salary must NOT hijack the numbers.
    The ranged '$X - $Y' phrase wins over the first-two-$ heuristic."""
    blob = "$5,000 signing bonus! Base pay $85,000 - $110,000 a year"
    assert _parse_salary(blob) == (85000.0, 110000.0)


def test_parse_salary_single_period_over_leading_promo():
    blob = "Up to $2,000 referral $30 per hour"
    lo, hi = _parse_salary(blob)
    assert lo == 30 * 2080 and hi is None


def test_parse_salary_period_yr_suffix():
    lo, hi = _parse_salary("Earn $95,000/yr plus a $1,000 bonus")
    assert lo == 95000.0 and hi is None


def test_parse_salary_to_range():
    assert _parse_salary("$85,000 to $110,000") == (85000.0, 110000.0)


# ── EXT-3: side-effecting POST is gated by request Origin ─────────────────────

def test_harvest_rejects_missing_origin(client):
    """An origin-less POST must be refused with 403 before any side effects."""
    resp = client.post("/harvest", json={"jobs": [{"title": "x", "url": "https://e.com/1"}]})
    assert resp.status_code == 403


def test_harvest_rejects_foreign_origin(client):
    resp = client.post(
        "/harvest",
        json={"jobs": [{"title": "x", "url": "https://e.com/1"}]},
        headers={"Origin": "https://evil.example.com"},
    )
    assert resp.status_code == 403


def test_harvest_accepts_chrome_extension_origin(client):
    """A chrome-extension Origin passes the gate (not 403). Empty jobs list ->
    400, which still proves the origin was accepted (rejection would be 403)."""
    resp = client.post(
        "/harvest",
        json={"jobs": []},
        headers={"Origin": "chrome-extension://abcdefghijklmnop"},
    )
    assert resp.status_code != 403
    assert resp.status_code == 400


def test_harvest_accepts_localhost_origin(client):
    resp = client.post(
        "/harvest",
        json={"jobs": []},
        headers={"Origin": "http://127.0.0.1:5002"},
    )
    assert resp.status_code != 403
    assert resp.status_code == 400


def test_origin_allowed_helper():
    assert _origin_allowed("chrome-extension://abcdef") is True
    assert _origin_allowed("http://localhost:5002") is True
    assert _origin_allowed("http://127.0.0.1:5002") is True
    assert _origin_allowed("") is False
    assert _origin_allowed("https://evil.example.com") is False
    assert _origin_allowed("http://10.0.0.5:5002") is False
