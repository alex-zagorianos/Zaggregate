"""Careers-cluster fixes (2026-06 review).

Covers:
  CAREERS-2  department text is NOT folded into the keyword match haystack
             (title-only gating); it still reaches the scorer via description.
  CAREERS-3  workday_scraper reads data['total'] into board_count.
  CAREERS-4  company_registry industry filter is symmetric (partial user tags
             survive a longer --industry key).
  CAREERS-5  direct_scraper and workday_scraper negative-cache via the shared
             cache_helpers is_failed/mark_failed JSON markers.
  CAREERS-6  discoverer recognizes ashby / smartrecruiters / workday URLs.
"""
import json

import requests

from models import JobResult
from scrape import (
    ashby_scraper,
    direct_scraper,
    greenhouse_scraper,
    lever_scraper,
    smartrecruiters_scraper,
    workday_scraper,
)
from scrape.cache_helpers import is_failed, mark_failed, read_cache
from scrape.company_registry import CompanyEntry, get_registry


class _Resp:
    """Minimal stand-in for a requests.Response."""

    def __init__(self, payload, *, text=None):
        self._payload = payload
        self.text = text if text is not None else ""

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


# ---------------------------------------------------------------------------
# CAREERS-2 — department text must not satisfy a title keyword
# ---------------------------------------------------------------------------
def _gh_payload():
    return {
        "meta": {"total": 5},
        "jobs": [{
            "id": 1,
            "title": "Senior Controls Technician",   # NOT "controls engineer"
            "departments": [{"name": "Controls Engineering"}],
            "location": {"name": "Peoria, IL"},
            "content": "Maintain PLCs and fixtures.",
            "absolute_url": "https://example.com/1",
            "first_published": "2026-06-01",
        }],
    }


def test_greenhouse_dept_not_in_match_haystack(tmp_path, monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **k: _Resp(_gh_payload()))
    company = CompanyEntry("Acme", "greenhouse", "acme")
    jobs = greenhouse_scraper.scrape_greenhouse(company, "controls engineer",
                                                tmp_path, cache_enabled=False)
    # "controls engineer" appears only in the DEPARTMENT, never the title.
    assert jobs == []


def test_greenhouse_dept_reaches_description(tmp_path, monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **k: _Resp(_gh_payload()))
    company = CompanyEntry("Acme", "greenhouse", "acme")
    # A title-matching keyword so the job survives; the dept must show up in the
    # description so the scorer's skill-overlap can read it.
    jobs = greenhouse_scraper.scrape_greenhouse(company, "controls technician",
                                                tmp_path, cache_enabled=False)
    assert len(jobs) == 1
    assert "Controls Engineering" in jobs[0].description


def test_greenhouse_url_is_server_rendered_embed(tmp_path, monkeypatch):
    # The saved link must be Greenhouse's hosted application URL (built from
    # slug + id), NOT the company's absolute_url which can be a dead JS SPA.
    monkeypatch.setattr(requests, "get", lambda *a, **k: _Resp(_gh_payload()))
    company = CompanyEntry("Acme", "greenhouse", "acme")
    jobs = greenhouse_scraper.scrape_greenhouse(company, "controls technician",
                                                tmp_path, cache_enabled=False)
    assert jobs[0].url == (
        "https://job-boards.greenhouse.io/embed/job_app?for=acme&token=1"
    )


def test_lever_dept_not_in_match_haystack(tmp_path, monkeypatch):
    payload = [{
        "id": "a1",
        "text": "Senior Controls Technician",
        "categories": {"team": "Controls Engineering", "department": "Engineering",
                       "location": "Remote"},
        "descriptionPlain": "Maintain PLCs.",
        "hostedUrl": "https://jobs.lever.co/acme/a1",
    }]
    monkeypatch.setattr(requests, "get", lambda *a, **k: _Resp(payload))
    company = CompanyEntry("Acme", "lever", "acme")
    assert lever_scraper.scrape_lever(company, "controls engineer", tmp_path,
                                      cache_enabled=False) == []
    # Title-matching keyword -> survives, dept in description.
    jobs = lever_scraper.scrape_lever(company, "controls technician", tmp_path,
                                      cache_enabled=False)
    assert len(jobs) == 1
    assert "Controls Engineering" in jobs[0].description


def test_ashby_dept_not_in_match_haystack(tmp_path, monkeypatch):
    payload = {"jobs": [{
        "id": "x1",
        "title": "Senior Controls Technician",
        "department": "Controls Engineering",
        "team": "Hardware",
        "location": "Pittsburgh, PA",
        "descriptionPlain": "Run the line.",
        "jobUrl": "https://jobs.ashbyhq.com/acme/x1",
        "isListed": True,
    }]}
    monkeypatch.setattr(requests, "get", lambda *a, **k: _Resp(payload))
    company = CompanyEntry("Acme", "ashby", "acme")
    assert ashby_scraper.scrape_ashby(company, "controls engineer", tmp_path,
                                      cache_enabled=False) == []
    jobs = ashby_scraper.scrape_ashby(company, "controls technician", tmp_path,
                                      cache_enabled=False)
    assert len(jobs) == 1
    assert "Controls Engineering" in jobs[0].description


def test_smartrecruiters_dept_not_in_match_haystack(tmp_path, monkeypatch):
    payload = {
        "totalFound": 3,
        "content": [{
            "id": "p1",
            "name": "Senior Controls Technician",
            "function": {"label": "Controls Engineering"},
            "department": {"label": "Operations"},
            "location": {"city": "Houston", "region": "TX", "country": "us"},
            "releasedDate": "2026-06-01",
        }],
    }
    monkeypatch.setattr(requests, "get", lambda *a, **k: _Resp(payload))
    # Avoid the per-match detail fetch by leaving it to return "".
    monkeypatch.setattr(smartrecruiters_scraper, "_fetch_description",
                        lambda *a, **k: "")
    company = CompanyEntry("Acme", "smartrecruiters", "acme")
    assert smartrecruiters_scraper.scrape_smartrecruiters(
        company, "controls engineer", tmp_path, cache_enabled=False) == []
    jobs = smartrecruiters_scraper.scrape_smartrecruiters(
        company, "controls technician", tmp_path, cache_enabled=False)
    assert len(jobs) == 1
    assert "Controls Engineering" in jobs[0].description


# ---------------------------------------------------------------------------
# CAREERS-3 — workday board_count from data['total']
# ---------------------------------------------------------------------------
def test_workday_reads_board_total(tmp_path, monkeypatch):
    payload = {
        "total": 287,
        "jobPostings": [{
            "title": "Controls Engineer",
            "locationsText": "Seguin, TX",
            "externalPath": "/job/Seguin/Controls-Engineer_R1",
            "reqId": "R1",
        }],
    }
    monkeypatch.setattr(requests, "post", lambda *a, **k: _Resp(payload))
    company = CompanyEntry("Caterpillar", "workday", "cat:5:CaterpillarCareers")
    jobs = workday_scraper.scrape_workday(company, "controls", tmp_path,
                                          cache_enabled=False)
    assert len(jobs) == 1
    assert jobs[0].board_count == 287


def test_workday_missing_total_stays_unknown(tmp_path, monkeypatch):
    payload = {"jobPostings": [{
        "title": "Controls Engineer", "locationsText": "TX",
        "externalPath": "/job/x_R2", "reqId": "R2"}]}
    monkeypatch.setattr(requests, "post", lambda *a, **k: _Resp(payload))
    company = CompanyEntry("Caterpillar", "workday", "cat:5:CaterpillarCareers")
    jobs = workday_scraper.scrape_workday(company, "controls", tmp_path,
                                          cache_enabled=False)
    assert jobs[0].board_count == -1


# ---------------------------------------------------------------------------
# CAREERS-4 — symmetric industry tag filter
# ---------------------------------------------------------------------------
def test_partial_user_tag_survives_longer_industry(tmp_path):
    companies = {"companies": [{
        "name": "User Controls Co",
        "ats_type": "greenhouse",
        "slug": "usercontrols",
        "industries": ["controls"],   # shorter than the --industry key
    }]}
    cfile = tmp_path / "companies.json"
    cfile.write_text(json.dumps(companies), encoding="utf-8")
    out = get_registry("controls_engineering", user_json=cfile)
    assert any(c.name == "User Controls Co" for c in out)


def test_unrelated_user_tag_still_filtered_out(tmp_path):
    companies = {"companies": [{
        "name": "Bakery Co",
        "ats_type": "greenhouse",
        "slug": "bakery",
        "industries": ["baking"],
    }]}
    cfile = tmp_path / "companies.json"
    cfile.write_text(json.dumps(companies), encoding="utf-8")
    out = get_registry("controls_engineering", user_json=cfile)
    assert not any(c.name == "Bakery Co" for c in out)


# ---------------------------------------------------------------------------
# CAREERS-5 — standardized negative-cache markers round-trip
# ---------------------------------------------------------------------------
def test_failed_marker_round_trips(tmp_path):
    f = tmp_path / "marker.json"
    assert is_failed(read_cache(f)) is False   # nothing yet
    mark_failed(f)
    assert is_failed(read_cache(f)) is True


def test_direct_scraper_negative_cache_skips_refetch(tmp_path, monkeypatch):
    calls = {"n": 0}

    def boom(*a, **k):
        calls["n"] += 1
        raise requests.ConnectionError("dead host")

    monkeypatch.setattr(requests, "get", boom)
    company = CompanyEntry("Dead Co", "direct", "https://dead.example/careers")

    # First call fails and writes the shared JSON failure marker.
    assert direct_scraper.scrape_direct(company, "controls", tmp_path,
                                        cache_enabled=True) == []
    assert calls["n"] == 1
    markers = list(tmp_path.glob("direct_*_FAILED.json"))
    assert len(markers) == 1
    assert is_failed(read_cache(markers[0])) is True

    # Second call sees the marker and does NOT re-fetch.
    assert direct_scraper.scrape_direct(company, "controls", tmp_path,
                                        cache_enabled=True) == []
    assert calls["n"] == 1  # no extra network attempt


def test_workday_negative_cache_uses_json_marker(tmp_path, monkeypatch):
    calls = {"n": 0}

    def boom(*a, **k):
        calls["n"] += 1
        raise requests.ConnectionError("dead tenant")

    monkeypatch.setattr(requests, "post", boom)
    company = CompanyEntry("Dead WD", "workday", "deadwd:1:Careers")

    assert workday_scraper.scrape_workday(company, "controls", tmp_path,
                                          cache_enabled=True) == []
    markers = list(tmp_path.glob("workday_*_FAILED.json"))
    assert len(markers) == 1
    assert is_failed(read_cache(markers[0])) is True

    assert workday_scraper.scrape_workday(company, "controls", tmp_path,
                                          cache_enabled=True) == []
    assert calls["n"] == 1  # marker short-circuits the second attempt


# ---------------------------------------------------------------------------
# CAREERS-6 — discovery recognizes the newer ATSes
# ---------------------------------------------------------------------------
def test_discoverer_sites_cover_new_atses():
    from scrape.discoverer import _ATS_SITES
    assert "jobs.ashbyhq.com" in _ATS_SITES.values()
    assert "jobs.smartrecruiters.com" in _ATS_SITES.values()
    assert any("myworkdayjobs.com" in s for s in _ATS_SITES.values())


def test_discoverer_extracts_entries_for_each_ats():
    from scrape.discoverer import _extract_entries

    # Ashby subdomain board.
    data = {"web": {"results": [{"url": "https://jobs.ashbyhq.com/gecko-robotics/x"}]}}
    out = _extract_entries(data, "jobs.ashbyhq.com")
    assert out and out[0][0] == "ashby" and out[0][1] == "gecko-robotics"

    # SmartRecruiters.
    data = {"web": {"results": [{"url": "https://jobs.smartrecruiters.com/AcmeCorp/12345"}]}}
    out = _extract_entries(data, "jobs.smartrecruiters.com")
    assert out and out[0][0] == "smartrecruiters" and out[0][1] == "AcmeCorp"

    # Workday public URL -> tenant:N:site slug.
    data = {"web": {"results": [
        {"url": "https://cat.wd5.myworkdayjobs.com/CaterpillarCareers/job/x_R1"}]}}
    out = _extract_entries(data, "myworkdayjobs.com")
    assert out and out[0][0] == "workday"
    assert out[0][1] == "cat:5:CaterpillarCareers"
