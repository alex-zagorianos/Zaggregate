from pathlib import Path
import requests
import scrape.personio_scraper as P

FX = Path(__file__).resolve().parents[1] / "fixtures" / "ws2"

class _Resp:
    def __init__(self, text):
        self.text = text
        self.content = text.encode("utf-8")
    def raise_for_status(self):
        pass

def _xml():
    return (FX / "personio.xml").read_text(encoding="utf-8")

def test_fetch_parses_xml(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **k: _Resp(_xml()))
    jobs = P.fetch("acme")
    assert len(jobs) == 2
    assert jobs[0].title == "Embedded Engineer"
    assert jobs[0].location == "Cincinnati"
    assert jobs[0].source_api == "careers"
    assert "firmware" in jobs[0].description.lower()
    assert jobs[0].job_id == "personio_9001"

def test_fetch_bad_xml_empty(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **k: _Resp("<not-xml"))
    assert P.fetch("acme") == []
