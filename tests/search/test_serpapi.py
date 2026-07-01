import json
from pathlib import Path
import pytest
import search.serpapi_client as SC
from search.serpapi_client import SerpApiClient

FX = Path(__file__).resolve().parents[1] / "fixtures" / "ws2"

def _payload():
    return json.loads((FX / "serpapi.json").read_text(encoding="utf-8"))

def test_init_no_key_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(SC, "SERPAPI_KEY", "")
    monkeypatch.setattr(SC.config, "SECRETS_DIR", tmp_path)  # no key file
    with pytest.raises(ValueError):
        SerpApiClient(cache_dir=tmp_path, cache_enabled=False)

def test_parse_maps(tmp_path, monkeypatch):
    monkeypatch.setattr(SC, "SERPAPI_KEY", "k")
    c = SerpApiClient(cache_dir=tmp_path, cache_enabled=False)
    jobs = c.parse_results(_payload(), "mechatronics engineer")
    assert len(jobs) == 1
    assert jobs[0].title == "Mechatronics Engineer"
    assert jobs[0].source_api == "serpapi"
    assert jobs[0].url.endswith("/mechatronics")

def test_quota_exhausted_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(SC, "SERPAPI_KEY", "k")
    c = SerpApiClient(cache_dir=tmp_path, cache_enabled=False)
    monkeypatch.setattr(c.quota, "try_increment", lambda n=1: False)
    assert c.search("x", "Cincinnati") == {"jobs_results": []}


class _Resp:
    def __init__(self, payload):
        self._payload = payload
    def raise_for_status(self):
        pass
    def json(self):
        return self._payload


def test_engine_configurable_and_in_cache_key(tmp_path, monkeypatch):
    monkeypatch.setattr(SC, "SERPAPI_KEY", "k")
    monkeypatch.setattr(SC.config, "SERPAPI_ENGINE", "indeed")
    c = SerpApiClient(cache_dir=tmp_path, cache_enabled=False)
    captured = {}

    def fake_get(url, params=None, timeout=None):
        captured.update(params)
        return _Resp({"jobs_results": []})

    monkeypatch.setattr(c.session, "get", fake_get)
    c.search("welder", "Cincinnati, OH")
    assert captured["engine"] == "indeed"
    assert captured["q"] == "welder" and captured["l"] == "Cincinnati, OH"


def test_parse_handles_indeed_shape_and_unknown(tmp_path, monkeypatch):
    monkeypatch.setattr(SC, "SERPAPI_KEY", "k")
    c = SerpApiClient(cache_dir=tmp_path, cache_enabled=False)
    indeed_shape = {"jobs_results": [{
        "title": "CNC Machinist", "company": "Acme Mfg", "location": "Cincinnati, OH",
        "link": "https://www.indeed.com/viewjob?jk=abc123", "job_key": "abc123",
        "snippet": "Operate CNC.", "date": "2 days ago",
    }]}
    jobs = c.parse_results(indeed_shape, "cnc")
    assert len(jobs) == 1 and jobs[0].company == "Acme Mfg"
    assert jobs[0].url.endswith("jk=abc123") and jobs[0].job_id == "serpapi_abc123"
    # unrecognized top-level shape -> [] (defensive, no raise)
    assert c.parse_results({"error": "Invalid engine"}, "cnc") == []
