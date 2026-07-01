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


def test_indeed_engine_empty_results_warns_once_on_stderr(tmp_path, monkeypatch, capsys):
    """engine='indeed' + no usable jobs_results -> a one-time stderr warning, never
    a silent zero (SerpApi's 2026 public catalog no longer documents a standalone
    Indeed engine — see brain/research-2026-07-01-reach-indeed-access.md)."""
    monkeypatch.setattr(SC, "SERPAPI_KEY", "k")
    monkeypatch.setattr(SC.config, "SERPAPI_ENGINE", "indeed")
    c = SerpApiClient(cache_dir=tmp_path, cache_enabled=False)
    monkeypatch.setattr(c.session, "get", lambda *a, **k: _Resp({"jobs_results": []}))

    result1 = c.search("welder", "Cincinnati, OH")
    result2 = c.search("machinist", "Cincinnati, OH")  # distinct keyword -> not cached

    assert result1 == {"jobs_results": []}
    assert result2 == {"jobs_results": []}
    err = capsys.readouterr().err
    assert "indeed" in err.lower()
    lines = [ln for ln in err.splitlines() if ln.strip()]
    assert len(lines) == 1, f"warning must fire exactly ONCE (across 2 calls), got: {lines}"


def test_google_jobs_engine_never_warns_on_empty(tmp_path, monkeypatch, capsys):
    """Default google_jobs engine returning empty is normal (no results found) —
    must NOT trigger the indeed-engine-unavailable warning."""
    monkeypatch.setattr(SC, "SERPAPI_KEY", "k")
    c = SerpApiClient(cache_dir=tmp_path, cache_enabled=False)
    monkeypatch.setattr(c.session, "get", lambda *a, **k: _Resp({"jobs_results": []}))

    c.search("welder", "Cincinnati, OH")
    assert capsys.readouterr().err == ""


def test_indeed_engine_with_results_does_not_warn(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(SC, "SERPAPI_KEY", "k")
    monkeypatch.setattr(SC.config, "SERPAPI_ENGINE", "indeed")
    c = SerpApiClient(cache_dir=tmp_path, cache_enabled=False)
    payload = {"jobs_results": [{"title": "Welder", "company": "Acme", "link": "https://x/1"}]}
    monkeypatch.setattr(c.session, "get", lambda *a, **k: _Resp(payload))

    c.search("welder", "Cincinnati, OH")
    assert capsys.readouterr().err == ""
