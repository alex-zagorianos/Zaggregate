import json
from pathlib import Path
import search.jooble_client as JC
from search.jooble_client import JoobleClient

FX = Path(__file__).resolve().parents[1] / "fixtures" / "ws2"

def _payload():
    return json.loads((FX / "jooble.json").read_text(encoding="utf-8"))

def test_parse_maps(tmp_path):
    c = JoobleClient(cache_dir=tmp_path, cache_enabled=False)
    jobs = c.parse_results(_payload(), "automation engineer")
    assert len(jobs) == 1
    assert jobs[0].title == "Automation Engineer"
    assert jobs[0].source_api == "jooble"
    assert "lines" in jobs[0].description  # html stripped
    assert jobs[0].url.endswith("/123")

def test_no_key_warns_and_empty(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(JC, "JOOBLE_API_KEY", "")
    c = JoobleClient(cache_dir=tmp_path, cache_enabled=False)
    assert c.search("automation engineer", "Cincinnati") == {"jobs": []}
    assert "WARNING" in capsys.readouterr().out
