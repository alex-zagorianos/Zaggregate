import json
from pathlib import Path

import search.socrata_client as SOC
from search.socrata_client import DatasetSpec, SocrataClient

FX = Path(__file__).resolve().parents[1] / "fixtures" / "socrata_nyc.json"


def _payload():
    return json.loads(FX.read_text(encoding="utf-8"))


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def test_default_constructor_has_no_cities(tmp_path):
    c = SocrataClient(cache_dir=tmp_path, cache_enabled=False)
    assert c.cities == []


def test_no_cities_configured_search_and_parse_returns_empty(tmp_path):
    c = SocrataClient(cache_dir=tmp_path, cache_enabled=False)
    assert c.search_and_parse("controls engineer", "Cincinnati", None, 1) == []
    # And no-op means no HTTP call was even attempted: search() alone is safe.
    assert c.search("controls engineer", page=1) == {}


def test_unknown_city_key_is_ignored(tmp_path):
    c = SocrataClient(cities=["nyc", "atlantis"], cache_dir=tmp_path, cache_enabled=False)
    assert c.cities == ["nyc"]


def test_search_and_parse_nyc_stubbed_fetch(tmp_path, monkeypatch):
    """NYC configured + a stubbed HTTP fetch returning the fixture -> the full
    search_and_parse round trip maps every row correctly."""
    c = SocrataClient(cities=["nyc"], cache_dir=tmp_path, cache_enabled=False)
    monkeypatch.setattr(c.session, "get", lambda *a, **k: _Resp(_payload()))

    jobs = c.search_and_parse("controls engineer", "Cincinnati", None, 1)

    assert len(jobs) == 3
    assert all(j.source_api == "socrata" for j in jobs)
    job = jobs[0]
    assert job.title == "Mechanical Engineer"
    assert job.company == "DEPT OF ENVIRONMENTAL PROTECTION"
    assert job.location == "Queens, NY"
    assert job.salary_min == 75000.0
    assert job.salary_max == 95000.0
    assert job.description.startswith("Design and maintain HVAC")
    assert job.created == "2026-06-01T00:00:00.000"
    assert job.job_id == "socrata_123456"
    assert job.url == "https://cityjobs.nyc.gov/jobs/123456"
    assert job.source_keyword == "controls engineer"


def test_parse_defensive_missing_salary_and_description(tmp_path):
    """Third fixture row has no salary_range_from/to or job_description ->
    None/"" rather than a raise (defensive .get() on every column)."""
    c = SocrataClient(cities=["nyc"], cache_dir=tmp_path, cache_enabled=False)
    jobs = c.parse_results({"nyc": _payload()}, "automation engineer")
    third = jobs[2]
    assert third.title == "Automation Engineer"
    assert third.salary_min is None
    assert third.salary_max is None
    assert third.description == ""


def test_second_dataset_spec_with_different_columns_maps_generically(tmp_path, monkeypatch):
    """A second city with entirely different column names still maps
    correctly through the SAME parse_results — proves adding a city is a
    pure-data change (new DatasetSpec), not a code change."""
    test_spec = DatasetSpec(
        domain="data.example.gov",
        dataset_id="abcd-1234",
        col_title="job_title",
        col_company="dept_name",
        col_location="site",
        col_salary_min="pay_min",
        col_salary_max="pay_max",
        col_desc="summary",
        col_posted="posted_on",
        col_id="rec_id",
        url_template="https://jobs.example.gov/{id}",
    )
    monkeypatch.setitem(SOC.SOCRATA_DATASETS, "testcity", test_spec)

    c = SocrataClient(cities=["testcity"], cache_dir=tmp_path, cache_enabled=False)
    raw = {"testcity": [{
        "rec_id": "999",
        "job_title": "Water Systems Engineer",
        "dept_name": "Public Works",
        "site": "Springfield, IL",
        "pay_min": "60000",
        "pay_max": "80000",
        "summary": "Maintain municipal water infrastructure.",
        "posted_on": "2026-06-15T00:00:00.000",
    }]}

    jobs = c.parse_results(raw, "water")

    assert len(jobs) == 1
    job = jobs[0]
    assert job.title == "Water Systems Engineer"
    assert job.company == "Public Works"
    assert job.location == "Springfield, IL"
    assert job.salary_min == 60000.0
    assert job.salary_max == 80000.0
    assert job.description == "Maintain municipal water infrastructure."
    assert job.url == "https://jobs.example.gov/999"
    assert job.job_id == "socrata_999"
    assert job.source_api == "socrata"


def test_keyword_passed_into_q_param(tmp_path, monkeypatch):
    c = SocrataClient(cities=["nyc"], cache_dir=tmp_path, cache_enabled=False)
    captured = {}

    def fake_get(url, headers=None, params=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured.update(params)
        return _Resp(_payload())

    monkeypatch.setattr(c.session, "get", fake_get)
    c.search("controls engineer", page=1)

    assert captured["$q"] == "controls engineer"
    assert captured["$offset"] == 0
    assert captured["url"] == "https://data.cityofnewyork.us/resource/kpav-sd4t.json"
    assert captured["headers"] == {}  # no token configured -> no header


def test_page_two_advances_offset_by_limit(tmp_path, monkeypatch):
    c = SocrataClient(cities=["nyc"], limit=50, cache_dir=tmp_path, cache_enabled=False)
    captured = {}

    def fake_get(url, headers=None, params=None, timeout=None):
        captured.update(params)
        return _Resp([])

    monkeypatch.setattr(c.session, "get", fake_get)
    c.search("engineer", page=2)

    assert captured["$offset"] == 50
    assert captured["$limit"] == 50


def test_app_token_sent_as_header_when_configured(tmp_path, monkeypatch):
    c = SocrataClient(cities=["nyc"], app_token="tok123", cache_dir=tmp_path, cache_enabled=False)
    captured = {}

    def fake_get(url, headers=None, params=None, timeout=None):
        captured["headers"] = headers
        return _Resp([])

    monkeypatch.setattr(c.session, "get", fake_get)
    c.search("engineer", page=1)

    assert captured["headers"] == {"X-App-Token": "tok123"}


def test_app_token_read_from_env(tmp_path, monkeypatch):
    monkeypatch.setenv("SOCRATA_APP_TOKEN", "env-tok")
    c = SocrataClient(cities=["nyc"], cache_dir=tmp_path, cache_enabled=False)
    assert c.app_token == "env-tok"
