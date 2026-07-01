import json
from pathlib import Path
import requests
import scrape.rippling_scraper as R
from tests.scrape._scrape_fakes import FakeResp as _Resp, patch_session

FX = Path(__file__).resolve().parents[1] / "fixtures" / "ws2"

def _payload():
    return json.loads((FX / "rippling.json").read_text(encoding="utf-8"))

def test_fetch_maps(monkeypatch):
    patch_session(monkeypatch, R, lambda *a, **k: _Resp(_payload()))
    jobs = R.fetch("acme")
    assert len(jobs) == 2
    assert jobs[0].title == "Test Engineer"
    assert "Cincinnati" in jobs[0].location
    assert jobs[0].source_api == "careers"
    assert jobs[0].url.endswith("/r1")

def test_fetch_error_empty(monkeypatch):
    patch_session(monkeypatch, R, lambda *a, **k: (_ for _ in ()).throw(requests.RequestException()))
    assert R.fetch("acme") == []
