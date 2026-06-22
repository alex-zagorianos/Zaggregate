import json
from pathlib import Path
from search.arbeitnow_client import ArbeitnowClient

FX = Path(__file__).resolve().parents[1] / "fixtures" / "ws2"

def _payload():
    return json.loads((FX / "arbeitnow.json").read_text(encoding="utf-8"))

def _client(tmp_path):
    return ArbeitnowClient(cache_dir=tmp_path, cache_enabled=False)

def test_parse_filters_by_keyword(tmp_path):
    jobs = _client(tmp_path).parse_results(_payload(), "controls engineer")
    assert len(jobs) == 1
    assert jobs[0].title == "Controls Engineer"
    assert jobs[0].source_api == "arbeitnow"
    assert "PLC" in jobs[0].description

def test_parse_no_match(tmp_path):
    assert _client(tmp_path).parse_results(_payload(), "neurosurgeon") == []

def test_page_two_empty(tmp_path, monkeypatch):
    c = _client(tmp_path)
    monkeypatch.setattr(c, "_cached", lambda *a, **k: _payload())
    assert c.search("controls engineer", page=2) == {"data": []}
