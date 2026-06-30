import json

from scrape.company_health import prune_companies


def _seed(path):
    path.write_text(json.dumps({
        "_comment": "keep me",
        "companies": [
            {"_example": "skip", "name": "Example", "ats_type": "greenhouse", "slug": "ex"},
            {"name": "Dead Co", "ats_type": "greenhouse", "slug": "deadco", "industries": []},
            {"name": "Live Co", "ats_type": "lever", "slug": "liveco", "industries": []},
        ],
    }), encoding="utf-8")


def _companies(path):
    return {c["slug"]: c for c in json.loads(path.read_text(encoding="utf-8"))["companies"]
            if "_example" not in c}


def test_prune_needs_threshold_consecutive_misses(tmp_path):
    cj, hp = tmp_path / "companies.json", tmp_path / "health.json"
    _seed(cj)
    probe = lambda e: {"deadco": False, "liveco": True}.get(e.slug)

    # First probe: dead streak = 1, not yet removed.
    removed = prune_companies(threshold=2, json_path=cj, health_path=hp, probe=probe)
    assert removed == []
    assert "deadco" in _companies(cj)
    assert json.loads(hp.read_text())["greenhouse:deadco"] == 1

    # Second consecutive miss: removed.
    removed = prune_companies(threshold=2, json_path=cj, health_path=hp, probe=probe)
    assert removed == ["Dead Co"]
    assert "deadco" not in _companies(cj)
    assert "liveco" in _companies(cj)            # live one untouched


def test_alive_resets_streak(tmp_path):
    cj, hp = tmp_path / "companies.json", tmp_path / "health.json"
    _seed(cj)
    hp.write_text(json.dumps({"greenhouse:deadco": 1}), encoding="utf-8")
    # Now it comes back alive -> streak reset, not removed even though it had 1.
    removed = prune_companies(threshold=2, json_path=cj, health_path=hp,
                              probe=lambda e: True)
    assert removed == []
    assert json.loads(hp.read_text())["greenhouse:deadco"] == 0


def test_unknown_probe_does_not_penalize(tmp_path):
    cj, hp = tmp_path / "companies.json", tmp_path / "health.json"
    _seed(cj)
    removed = prune_companies(threshold=1, json_path=cj, health_path=hp,
                              probe=lambda e: None)  # outage / timeout
    assert removed == []
    assert _companies(cj).keys() == {"deadco", "liveco"}


def test_threshold_one_immediate(tmp_path):
    cj, hp = tmp_path / "companies.json", tmp_path / "health.json"
    _seed(cj)
    removed = prune_companies(threshold=1, json_path=cj, health_path=hp,
                              probe=lambda e: e.slug != "liveco" and False or (e.slug == "liveco"))
    # deadco -> False -> removed at threshold 1; liveco -> True -> kept
    assert removed == ["Dead Co"]
    assert "_comment" in json.loads(cj.read_text())          # comment preserved
    assert any(c.get("_example") for c in json.loads(cj.read_text())["companies"])
