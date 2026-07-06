import pytest

from datetime import date, timedelta

from scrape.browser_receiver import (
    _created_from_age,
    _origin_allowed,
    _parse_salary,
    _safe_http_url,
    _to_job_result,
    app,
    parse_details,
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


def _harvest_hermetic(monkeypatch, tmp_path):
    """Stub the side-effecting bits of harvest() (report files, browser tab,
    capture counter, output dir) so a full /harvest POST runs without touching the
    real workspace, and return nothing — the caller drives the request."""
    from scrape import browser_receiver as br
    monkeypatch.setattr(br.workspace, "output_dir", lambda slug=None: tmp_path)
    monkeypatch.setattr(br, "generate_html_report", lambda *a, **k: None)
    monkeypatch.setattr(br, "generate_csv_report", lambda *a, **k: None)
    monkeypatch.setattr(br.webbrowser, "open", lambda *a, **k: None)
    monkeypatch.setattr(br, "_bump_capture", lambda *a, **k: None)


def test_harvest_inbox_failure_surfaces_error_not_silent_drop(
        client, monkeypatch, tmp_path):
    """A scoring/DB failure during inbox routing must NOT report a clean
    inboxed:0 (indistinguishable from success). The capture succeeded (report
    saved) so it stays HTTP 200, but the response carries an additive
    ``inbox_error`` field so the extension can tell the user their hand-picked
    jobs were NOT triaged — the project's 'surface, don't silently drop' rule."""
    _harvest_hermetic(monkeypatch, tmp_path)
    # Force the inbox-routing block to blow up exactly where score_jobs runs.
    import match.scorer as scorer
    def _boom(*a, **k):
        raise RuntimeError("scorer exploded")
    monkeypatch.setattr(scorer, "score_jobs", _boom)

    resp = client.post(
        "/harvest",
        json={"jobs": [{"title": "Nurse", "url": "https://e.com/1"}],
              "open_report": False},
        headers={"Origin": "chrome-extension://abcdefghijklmnop"},
    )
    assert resp.status_code == 200          # capture itself succeeded
    data = resp.get_json()
    assert data["received"] == 1
    assert data["inboxed"] == 0
    # The failure is surfaced, not hidden — an additive field the extension reads.
    assert "inbox_error" in data
    assert "scorer exploded" in data["inbox_error"]


def test_harvest_success_has_no_inbox_error_field(client, monkeypatch, tmp_path):
    """The happy path is byte-shape identical to before the S40 fix: no
    ``inbox_error`` key (additive-only means old extension builds are unaffected)."""
    _harvest_hermetic(monkeypatch, tmp_path)
    import match.scorer as scorer
    from tracker import db as trackerdb
    monkeypatch.setattr(scorer, "score_jobs", lambda results, **k: results)
    monkeypatch.setattr(trackerdb, "init_db", lambda *a, **k: False)
    monkeypatch.setattr(trackerdb, "inbox_add_many", lambda scored: len(scored))

    resp = client.post(
        "/harvest",
        json={"jobs": [{"title": "Nurse", "url": "https://e.com/1"}],
              "open_report": False},
        headers={"Origin": "chrome-extension://abcdefghijklmnop"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert "inbox_error" not in data       # additive-only: absent on success
    assert data["inboxed"] == 1


def test_origin_allowed_helper():
    assert _origin_allowed("chrome-extension://abcdef") is True
    assert _origin_allowed("http://localhost:5002") is True
    assert _origin_allowed("http://127.0.0.1:5002") is True
    assert _origin_allowed("") is False
    assert _origin_allowed("https://evil.example.com") is False
    assert _origin_allowed("http://10.0.0.5:5002") is False


# ── detail-pane parsing (single source of truth, like salary) ─────────────────

def test_parse_details_linkedin_blob():
    blob = ("Cincinnati, OH · 3 days ago · 47 applicants\n"
            "Remote\nFull-time\nMid-Senior level\nEasy Apply")
    d = parse_details(blob)
    assert d["work_mode"] == "Remote"
    assert d["employment_type"] == "Full-time"
    assert d["seniority"] == "Mid-Senior level"
    assert d["applicants"] == 47
    assert d["posted_age_days"] == 3
    assert d["easy_apply"] is True


def test_parse_details_over_and_first_n_applicants():
    assert parse_details("Over 200 applicants")["applicants"] == 200
    assert parse_details("Be among the first 25 applicants")["applicants"] == 25


def test_parse_details_age_units_take_most_recent():
    # weeks/months convert to days; the smallest (most recent) wins.
    assert parse_details("Reposted 2 weeks ago")["posted_age_days"] == 14
    assert parse_details("1 month ago, updated 3 days ago")["posted_age_days"] == 3
    assert parse_details("1 hour ago")["posted_age_days"] == 0


def test_parse_details_empty_is_all_blank():
    d = parse_details("")
    assert d == {"work_mode": "", "employment_type": "", "seniority": "",
                 "applicants": None, "posted_age_days": None, "easy_apply": False}


def test_parse_details_hybrid_contract_indeed():
    d = parse_details("Hybrid work\nContract\nEasily apply")
    assert d["work_mode"] == "Hybrid"
    assert d["employment_type"] == "Contract"
    assert d["easy_apply"] is True


def test_created_from_age():
    assert _created_from_age(None) is None
    assert _created_from_age(0) == date.today().isoformat()
    assert _created_from_age(7) == (date.today() - timedelta(days=7)).isoformat()


# ── _to_job_result threads description + posting date + browse extras ─────────

def test_to_job_result_threads_description():
    job = {"title": "Controls Engineer", "url": "https://example.com/1",
           "company": "Acme", "description": "We use PLCs and Python. ROS a plus."}
    r = _to_job_result(job)
    assert "PLCs" in r.description          # body now flows through (was always "")


def test_to_job_result_uses_posting_age_for_created():
    job = {"title": "Eng", "url": "https://example.com/2",
           "details_text": "5 days ago · 10 applicants"}
    r = _to_job_result(job)
    assert r.created == (date.today() - timedelta(days=5)).isoformat()


def test_to_job_result_attaches_browse_extras():
    job = {"title": "Eng", "url": "https://example.com/3", "detailed": True,
           "external_id": "4099887766", "card_text": "Promoted · Easy Apply",
           "details_text": "Remote\nFull-time\nMid-Senior level\n88 applicants"}
    r = _to_job_result(job)
    b = r._extras["browse"]
    assert b["work_mode"] == "Remote"
    assert b["employment_type"] == "Full-time"
    assert b["seniority"] == "Mid-Senior level"
    assert b["applicants"] == 88
    assert b["easy_apply"] is True
    assert b["promoted"] is True
    assert b["external_id"] == "4099887766"
    assert b["detailed"] is True


def test_to_job_result_no_extras_when_card_only():
    # A plain card (no detail blob, no promoted/easy-apply) carries no _extras,
    # so non-browser pipelines and daily_run are unaffected.
    job = {"title": "Eng", "url": "https://example.com/4", "company": "Acme"}
    r = _to_job_result(job)
    assert not hasattr(r, "_extras")
