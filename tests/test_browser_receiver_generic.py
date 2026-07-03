"""S33 site-agnostic capture: the browser extension's generic "Capture this job"
path forwards schema.org JobPosting JSON-LD (or a DOM-scrape fallback) to the
receiver in the SAME job-dict shape as the aggregator path. There's no JS test
harness, so these tests exercise the SERVER side of that contract:

  * a JSON-LD-shaped payload (annual numeric salary, explicit posted_iso,
    employmentType in details_text, a real description) -> a JobResult with the
    right created/salary/description and source_api "page_browser";
  * a bad posted_iso falls back gracefully (no crash, uses the age/capture date);
  * an hourly composed salary_text annualizes via the server's one salary parser;
  * a DOM-fallback-shaped payload (no salary, description only) still inboxes.

The JSON-LD extraction itself lives in browser_ext/generic_capture.js (the
injected function); here we pin the receiver's honoring of the new fields.
"""
from datetime import date, datetime, timedelta, timezone

import pytest

from scrape.browser_receiver import _iso_date_prefix, _to_job_result, app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    return app.test_client()


# The Origin the extension's fetch carries; the /harvest gate accepts it. A
# per-install chrome-extension:// origin is unguessable, so this proves the
# origin was ACCEPTED (a foreign/absent origin would 403 before any parsing).
EXT_ORIGIN = {"Origin": "chrome-extension://abcdefghijklmnop"}


# ── _iso_date_prefix helper (schema.org datePosted -> calendar day) ───────────

@pytest.mark.parametrize("value,expected", [
    ("2026-06-30", "2026-06-30"),
    ("2026-06-30T09:00:00Z", "2026-06-30"),
    ("2026-06-30T09:00:00+02:00", "2026-06-30"),
    ("  2026-01-05T00:00:00  ", "2026-01-05"),
])
def test_iso_date_prefix_parses_valid(value, expected):
    assert _iso_date_prefix(value) == expected


@pytest.mark.parametrize("value", [
    None, "", "not-a-date", "June 30 2026", "2026/06/30",
    "2026-13-40",       # well-shaped but impossible -> rejected
    20260630,           # not a string
    "20260630",         # no dashes
])
def test_iso_date_prefix_rejects_junk(value):
    assert _iso_date_prefix(value) is None


# ── JSON-LD-shaped payload: the happy path ────────────────────────────────────

def test_jsonld_payload_maps_all_fields():
    """A JobPosting-derived payload: annual numeric salary, explicit posted_iso,
    employmentType in details_text, description present. The receiver honors each
    and stamps source_api from source="page"."""
    job = {
        "title": "Controls Engineer",
        "company": "Acme Robotics",
        "location": "Cincinnati, OH",
        "url": "https://careers.acme.com/jobs/4567890",
        "salary_min": 95000,
        "salary_max": 120000,
        "description": "Own our PLC/robotics stack. Python and ROS a plus.",
        "details_text": "Full-time\nRemote",
        "source": "page",
        "detailed": True,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "posted_iso": "2026-06-30T09:00:00Z",
    }
    r = _to_job_result(job)
    assert r is not None
    assert r.title == "Controls Engineer"
    assert r.company == "Acme Robotics"
    # source="page" -> "page_browser" (existing f"{source}_browser" contract).
    assert r.source_api == "page_browser"
    # Annual numerics flow straight through (no text parsing needed).
    assert r.salary_min == 95000 and r.salary_max == 120000
    assert "PLC" in r.description
    # posted_iso wins the created precedence over the capture timestamp.
    assert r.created == "2026-06-30"
    # details_text parsed server-side into the browse extras.
    b = r._extras["browse"]
    assert b["employment_type"] == "Full-time"
    assert b["work_mode"] == "Remote"
    assert b["detailed"] is True


def test_jsonld_posted_iso_beats_age_derived_created():
    """When BOTH an explicit posted_iso and an age hint ('N days ago') are
    present, the exact ISO date wins — it's the stronger signal."""
    job = {
        "title": "Eng",
        "url": "https://careers.acme.com/jobs/1",
        "source": "page",
        "details_text": "5 days ago",          # would derive today-5
        "posted_iso": "2026-01-15",             # exact date -> should win
    }
    r = _to_job_result(job)
    assert r.created == "2026-01-15"


def test_jsonld_bad_posted_iso_falls_back_gracefully():
    """Junk in posted_iso must not crash and must not override — the age-derived
    date (from details_text) is used instead."""
    job = {
        "title": "Eng",
        "url": "https://careers.acme.com/jobs/2",
        "source": "page",
        "details_text": "3 days ago",
        "posted_iso": "sometime last week",     # unparseable
    }
    r = _to_job_result(job)
    # Falls back to the "N days ago" derivation, not a raise, not the junk value.
    assert r.created == (date.today() - timedelta(days=3)).isoformat()


def test_jsonld_no_posted_iso_uses_captured_at():
    """No posted_iso and no age hint -> the capture timestamp stands."""
    cap = "2026-02-02T12:00:00+00:00"
    job = {
        "title": "Eng",
        "url": "https://careers.acme.com/jobs/3",
        "source": "page",
        "captured_at": cap,
    }
    r = _to_job_result(job)
    assert r.created == cap


# ── hourly composed salary_text annualizes (the non-YEAR unit path) ───────────

def test_hourly_composed_salary_text_annualizes():
    """When the JSON-LD unit isn't YEAR, generic_capture.js composes a
    salary_text like '$38.50/hour' (no salary_min); the server's one salary
    parser annualizes it — same code that handles aggregator hourly text."""
    job = {
        "title": "Warehouse Associate",
        "url": "https://careers.bigbox.com/jobs/9",
        "source": "page",
        "salary_text": "$38.50/hour",
    }
    r = _to_job_result(job)
    assert r.salary_min == pytest.approx(38.50 * 2080)
    assert r.salary_max is None


def test_hourly_composed_salary_range_annualizes():
    job = {
        "title": "Tech",
        "url": "https://careers.bigbox.com/jobs/10",
        "source": "page",
        "salary_text": "$25 - $32/hour",
    }
    r = _to_job_result(job)
    assert r.salary_min == pytest.approx(25 * 2080)
    assert r.salary_max == pytest.approx(32 * 2080)


# ── DOM-fallback-shaped payload (no salary, description only) still inboxes ────

def test_dom_fallback_payload_is_valid_result():
    """The best-effort DOM path sends title + description (no salary, no
    location, no structured details). It must still parse into a JobResult."""
    job = {
        "title": "Software Engineer",
        "company": "Startup Inc",
        "location": "",
        "url": "https://startup.example/careers/swe",
        "salary_text": "",
        "description": "We are hiring a backend engineer. Go and Postgres.",
        "details_text": "",
        "source": "page",
        "detailed": True,
        "captured_at": datetime.now(timezone.utc).isoformat(),
    }
    r = _to_job_result(job)
    assert r is not None
    assert r.title == "Software Engineer"
    assert r.source_api == "page_browser"
    assert r.salary_min is None and r.salary_max is None
    assert "backend" in r.description


# ── /harvest route round-trip with the extension origin ───────────────────────

def test_harvest_route_accepts_page_source_payload(client, monkeypatch, tmp_path):
    """End-to-end through the /harvest handler with a chrome-extension Origin: a
    single 'page'-source JSON-LD job is received and inboxed — into a TMP
    tracker DB. The DB_PATH override matters: without it this test's fixture row
    leaked into the user's real ACTIVE project on every suite run (found live in
    test-controls' inbox during the S33 smoke — the docstring claimed isolation
    it didn't have)."""
    import scrape.browser_receiver as br
    import tracker.db as db

    monkeypatch.setattr(br.webbrowser, "open", lambda *a, **k: None)
    # Don't let report generation or inbox routing depend on a real project.
    monkeypatch.setattr(br, "generate_html_report", lambda *a, **k: None)
    monkeypatch.setattr(br, "generate_csv_report", lambda *a, **k: None)
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "tracker.db")

    job = {
        "title": "Controls Engineer",
        "company": "Acme",
        "location": "Cincinnati, OH",
        "url": "https://careers.acme.com/jobs/777",
        "salary_min": 90000,
        "salary_max": 110000,
        "description": "PLC and robotics.",
        "details_text": "Full-time\nRemote",
        "source": "page",
        "detailed": True,
        "posted_iso": "2026-06-30",
    }
    resp = client.post("/harvest", json={"jobs": [job]}, headers=EXT_ORIGIN)
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["received"] == 1
    # Inboxed into the TMP db — provable now that the write is isolated.
    assert body["inboxed"] == 1
    import sqlite3
    con = sqlite3.connect(tmp_path / "tracker.db")
    n = con.execute("SELECT COUNT(*) FROM inbox WHERE company = 'Acme'").fetchone()[0]
    con.close()
    assert n == 1
