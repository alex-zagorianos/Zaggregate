import json
from pathlib import Path
import requests
import scrape.workable_scraper as W

FX = Path(__file__).resolve().parents[1] / "fixtures" / "ws2"

class _Resp:
    def __init__(self, payload):
        self._p = payload
    def raise_for_status(self):
        pass
    def json(self):
        return self._p

def _payload():
    return json.loads((FX / "workable.json").read_text(encoding="utf-8"))

def test_fetch_maps_jobresults(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **k: _Resp(_payload()))
    jobs = W.fetch("acme")
    assert len(jobs) == 2
    j = jobs[0]
    assert j.title == "Controls Engineer"
    assert j.company == "Acme"
    assert "Cincinnati" in j.location
    assert j.source_api == "careers"
    assert j.url.endswith("/ABC123/")
    assert "PLC" in j.description  # HTML stripped, text kept

def test_fetch_http_error_returns_empty(monkeypatch):
    def boom(*a, **k):
        raise requests.RequestException("down")
    monkeypatch.setattr(requests, "get", boom)
    assert W.fetch("acme") == []
