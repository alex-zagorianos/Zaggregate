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
