from pathlib import Path
from search.linkedin_guest_client import LinkedInGuestClient

FX = Path(__file__).resolve().parents[1] / "fixtures" / "ws2"

def _html():
    return (FX / "linkedin_guest.html").read_text(encoding="utf-8")

def _client(tmp_path):
    return LinkedInGuestClient(cache_dir=tmp_path, cache_enabled=False)

def test_parse_cards(tmp_path):
    jobs = _client(tmp_path).parse_results({"html": _html()}, "controls engineer")
    assert len(jobs) == 2
    j = jobs[0]
    assert j.title == "Controls Engineer"
    assert j.company == "Acme Industries"
    assert "Cincinnati" in j.location
    assert j.url.endswith("/123456")
    assert j.source_api == "linkedin_guest"
    assert j.created == "2026-06-09"

def test_empty_html(tmp_path):
    assert _client(tmp_path).parse_results({"html": ""}, "x") == []
