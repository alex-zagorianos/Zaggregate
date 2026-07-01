import json
from pathlib import Path
import config
from search.careerjet_client import CareerjetClient

FX = Path(__file__).resolve().parents[1] / "fixtures" / "ws2"

def _payload():
    return json.loads((FX / "careerjet.json").read_text(encoding="utf-8"))

def test_parse_maps(tmp_path):
    c = CareerjetClient(cache_dir=tmp_path, cache_enabled=False)
    jobs = c.parse_results(_payload(), "test engineer")
    assert len(jobs) == 1
    assert jobs[0].title == "Test Engineer"
    assert jobs[0].source_api == "careerjet"
    assert jobs[0].salary_min == 80000 and jobs[0].salary_max == 100000
    assert "tests" in jobs[0].description

def test_no_affid_warns_and_empty(tmp_path, monkeypatch, capsys):
    # Affid now resolves env-then-secret at call time: clear both so it's unset.
    monkeypatch.delenv("CAREERJET_AFFID", raising=False)
    monkeypatch.setattr(config, "SECRETS_DIR", tmp_path / "no_secrets")
    c = CareerjetClient(cache_dir=tmp_path, cache_enabled=False)
    assert c.search("test engineer", "Cincinnati") == {"jobs": []}
    assert "WARNING" in capsys.readouterr().out
