from pathlib import Path
import scrape.personio_scraper as P
from tests.scrape._scrape_fakes import FakeResp, patch_session

FX = Path(__file__).resolve().parents[1] / "fixtures" / "ws2"

def _resp(text):
    return FakeResp(text=text)

def _xml():
    return (FX / "personio.xml").read_text(encoding="utf-8")

def test_fetch_parses_xml(monkeypatch):
    patch_session(monkeypatch, P, lambda *a, **k: _resp(_xml()))
    jobs = P.fetch("acme")
    assert len(jobs) == 2
    assert jobs[0].title == "Embedded Engineer"
    assert jobs[0].location == "Cincinnati"
    assert jobs[0].source_api == "careers"
    assert "firmware" in jobs[0].description.lower()
    assert jobs[0].job_id == "personio_9001"

def test_fetch_bad_xml_empty(monkeypatch):
    patch_session(monkeypatch, P, lambda *a, **k: _resp("<not-xml"))
    assert P.fetch("acme") == []
