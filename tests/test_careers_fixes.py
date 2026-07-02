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
from tests.scrape._scrape_fakes import patch_session


def _patch_wd_post(monkeypatch, post_fn):
    """Workday's jobs POST now runs through the shared retry session
    (_make_session); patch that instead of the global requests.post."""
    class _S:
        def post(self, *a, **k):
            return post_fn(*a, **k)
    monkeypatch.setattr(workday_scraper, "_make_session", lambda *a, **k: _S())


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
    patch_session(monkeypatch, ashby_scraper, lambda *a, **k: _Resp(payload))
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
    patch_session(monkeypatch, smartrecruiters_scraper, lambda *a, **k: _Resp(payload))
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
    _patch_wd_post(monkeypatch, lambda *a, **k: _Resp(payload))
    company = CompanyEntry("Caterpillar", "workday", "cat:5:CaterpillarCareers")
    jobs = workday_scraper.scrape_workday(company, "controls", tmp_path,
                                          cache_enabled=False)
    assert len(jobs) == 1
    assert jobs[0].board_count == 287


def test_workday_missing_total_stays_unknown(tmp_path, monkeypatch):
    payload = {"jobPostings": [{
        "title": "Controls Engineer", "locationsText": "TX",
        "externalPath": "/job/x_R2", "reqId": "R2"}]}
    _patch_wd_post(monkeypatch, lambda *a, **k: _Resp(payload))
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


class _StatusResp:
    """A response carrying an HTTP status (for the transient/permanent split)."""
    def __init__(self, status_code):
        self.status_code = status_code
    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")
    def json(self):
        return {}


def test_workday_permanent_404_negative_caches(tmp_path, monkeypatch):
    # A 404 (board removed/renamed) is PERMANENT -> negative-cache it so the run
    # doesn't re-probe a dead tenant every day for a week.
    calls = {"n": 0}

    def gone(*a, **k):
        calls["n"] += 1
        return _StatusResp(404)

    _patch_wd_post(monkeypatch, gone)
    company = CompanyEntry("Dead WD", "workday", "deadwd:1:Careers")

    assert workday_scraper.scrape_workday(company, "controls", tmp_path,
                                          cache_enabled=True) == []
    markers = list(tmp_path.glob("workday_*_FAILED.json"))
    assert len(markers) == 1
    assert is_failed(read_cache(markers[0])) is True

    assert workday_scraper.scrape_workday(company, "controls", tmp_path,
                                          cache_enabled=True) == []
    assert calls["n"] == 1  # marker short-circuits the second attempt


def test_workday_transient_does_not_negative_cache(tmp_path, monkeypatch):
    # A 429/5xx/network blip is TRANSIENT -> the board must NOT be poisoned for a
    # week (the self-inflicted-429 under-coverage bug). No _FAILED marker written,
    # and the board is re-attempted on the next run.
    calls = {"n": 0}

    def throttled(*a, **k):
        calls["n"] += 1
        return _StatusResp(429)

    _patch_wd_post(monkeypatch, throttled)
    company = CompanyEntry("Busy WD", "workday", "busywd:1:Careers")

    assert workday_scraper.scrape_workday(company, "controls", tmp_path,
                                          cache_enabled=True) == []
    assert list(tmp_path.glob("workday_*_FAILED.json")) == []  # not poisoned

    # A network exception is also transient (no marker, re-attempted).
    def boom(*a, **k):
        calls["n"] += 1
        raise requests.ConnectionError("blip")

    _patch_wd_post(monkeypatch, boom)
    assert workday_scraper.scrape_workday(company, "controls", tmp_path,
                                          cache_enabled=True) == []
    assert list(tmp_path.glob("workday_*_FAILED.json")) == []
    assert calls["n"] == 2  # both attempts actually ran (no short-circuit marker)


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


# ---------------------------------------------------------------------------
# SmartRecruiters fetcher — parse/map, keyword filter, display-name preference,
# public job URL, and permanent-404 negative-cache short-circuit.
# ---------------------------------------------------------------------------
def _sr_payload():
    return {
        "totalFound": 42,
        "content": [
            {
                "id": "744000133907678",
                "name": "Senior Management Consultant",
                "function": {"label": "Advisory"},
                "department": {"label": "Strategy"},
                "location": {"city": "Austin", "region": "TX", "country": "us",
                             "remote": False},
                "releasedDate": "2026-06-24T10:00:11.853Z",
                "ref": "https://api.smartrecruiters.com/v1/companies/visa/postings/744000133907678",
            },
            {
                "id": "744000120624847",
                "name": "Barista",
                "function": {"label": "Food Service"},
                "department": {"label": "Retail"},
                "location": {"city": "London", "region": "England", "country": "gb",
                             "remote": False},
                "releasedDate": "2026-04-14T07:57:07.974Z",
            },
        ],
    }


def test_smartrecruiters_maps(tmp_path, monkeypatch):
    patch_session(monkeypatch, smartrecruiters_scraper,
                  lambda *a, **k: _Resp(_sr_payload()))
    monkeypatch.setattr(smartrecruiters_scraper, "_fetch_description",
                        lambda *a, **k: "")
    company = CompanyEntry("Visa Inc.", "smartrecruiters", "visa")
    jobs = smartrecruiters_scraper.scrape_smartrecruiters(
        company, "consultant", tmp_path, cache_enabled=False)
    assert len(jobs) == 1                              # only the consultant title matches
    j = jobs[0]
    assert j.title == "Senior Management Consultant"
    assert j.location == "Austin, TX, us"              # city, region, country joined
    assert j.source_api == "careers"
    assert j.job_id == "smartrecruiters_744000133907678"
    # Public job URL built from the registry slug + posting id (verified live).
    assert j.url == "https://jobs.smartrecruiters.com/visa/744000133907678"
    # board_count reflects totalFound, not just this page's length.
    assert j.board_count == 42
    # function/department reach the scorer via the description (not the match haystack).
    assert "Advisory" in j.description and "Strategy" in j.description


def test_smartrecruiters_keyword_filter(tmp_path, monkeypatch):
    patch_session(monkeypatch, smartrecruiters_scraper,
                  lambda *a, **k: _Resp(_sr_payload()))
    monkeypatch.setattr(smartrecruiters_scraper, "_fetch_description",
                        lambda *a, **k: "")
    company = CompanyEntry("Visa Inc.", "smartrecruiters", "visa")
    jobs = smartrecruiters_scraper.scrape_smartrecruiters(
        company, "barista", tmp_path, cache_enabled=False)
    assert [j.title for j in jobs] == ["Barista"]


def test_smartrecruiters_uses_registry_display_name(tmp_path, monkeypatch):
    # The slug ("visa") is an opaque tenant id; the scorer's per-company inbox cap
    # and the UI want the registry display name, not a title-cased slug.
    patch_session(monkeypatch, smartrecruiters_scraper,
                  lambda *a, **k: _Resp(_sr_payload()))
    monkeypatch.setattr(smartrecruiters_scraper, "_fetch_description",
                        lambda *a, **k: "")
    company = CompanyEntry("Visa Inc.", "smartrecruiters", "visa")
    jobs = smartrecruiters_scraper.scrape_smartrecruiters(
        company, "consultant", tmp_path, cache_enabled=False)
    assert jobs and all(j.company == "Visa Inc." for j in jobs)


def test_smartrecruiters_permanent_404_negative_caches(tmp_path, monkeypatch):
    # A 404 (tenant removed/renamed) is PERMANENT -> negative-cached in the shared
    # cache file so the run doesn't re-probe a dead tenant for the TTL window.
    calls = {"n": 0}

    def gone(*a, **k):
        calls["n"] += 1
        return _StatusResp(404)

    patch_session(monkeypatch, smartrecruiters_scraper, gone)
    company = CompanyEntry("Dead SR", "smartrecruiters", "deadsr")

    assert smartrecruiters_scraper.scrape_smartrecruiters(
        company, "consultant", tmp_path, cache_enabled=True) == []
    assert calls["n"] == 1
    marker = tmp_path / "smartrecruiters_deadsr.json"
    assert is_failed(read_cache(marker)) is True

    # Second call sees the marker and does NOT re-fetch.
    assert smartrecruiters_scraper.scrape_smartrecruiters(
        company, "consultant", tmp_path, cache_enabled=True) == []
    assert calls["n"] == 1  # marker short-circuits the second attempt


def test_smartrecruiters_error_soft(tmp_path, monkeypatch):
    patch_session(monkeypatch, smartrecruiters_scraper,
                  lambda *a, **k: (_ for _ in ()).throw(requests.RequestException()))
    company = CompanyEntry("Acme", "smartrecruiters", "acme")
    assert smartrecruiters_scraper.scrape_smartrecruiters(
        company, "consultant", tmp_path, cache_enabled=False) == []


def test_dispatch_smartrecruiters(tmp_path, monkeypatch):
    # careers_client routes ats_type == "smartrecruiters" to scrape_smartrecruiters,
    # passing the whole CompanyEntry (so company.name -> the display name).
    import scrape.careers_client as cc
    captured = {}

    def stub(company, keyword, cache_dir, cache_enabled):
        captured["company"] = company
        captured["keyword"] = keyword
        return []

    monkeypatch.setattr(cc, "scrape_smartrecruiters", stub)
    client = cc.CareersClient(cache_dir=tmp_path, cache_enabled=False,
                              discovery_enabled=False)
    company = CompanyEntry("Visa Inc.", "smartrecruiters", "visa")
    client._scrape_one(company, "consultant")
    assert captured["company"].name == "Visa Inc."
    assert captured["company"].slug == "visa"
    assert captured["keyword"] == "consultant"
