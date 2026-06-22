import json
from pathlib import Path
import requests
import scrape.rippling_scraper as R

FX = Path(__file__).resolve().parents[1] / "fixtures" / "ws2"

class _Resp:
    def __init__(self, payload):
        self._p = payload
    def raise_for_status(self):
        pass
    def json(self):
        return self._p

def _payload():
    return json.loads((FX / "rippling.json").read_text(encoding="utf-8"))

def test_fetch_maps(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **k: _Resp(_payload()))
    jobs = R.fetch("acme")
    assert len(jobs) == 2
    assert jobs[0].title == "Test Engineer"
    assert "Cincinnati" in jobs[0].location
    assert jobs[0].source_api == "careers"
    assert jobs[0].url.endswith("/r1")

def test_fetch_error_empty(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **k: (_ for _ in ()).throw(requests.RequestException()))
    assert R.fetch("acme") == []
