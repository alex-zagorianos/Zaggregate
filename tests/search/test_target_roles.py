import json
import preferences

def test_default_hard_has_target_roles():
    assert "target_roles" in preferences._DEFAULT_HARD
    assert preferences._DEFAULT_HARD["target_roles"] == []

def test_migrate_seeds_target_roles_from_keywords():
    cfg = {"keywords": ["controls engineer", "automation engineer"], "location": "Cincinnati"}
    out = preferences.migrate_from_user_config(cfg)
    assert out["hard"]["target_roles"] == ["controls engineer", "automation engineer"]

def test_load_carries_target_roles(tmp_path):
    pj = tmp_path / "preferences.json"
    pj.write_text(json.dumps({"target_roles": ["mechatronics engineer"], "locations": ["Cincinnati"]}),
                  encoding="utf-8")
    loaded = preferences.load(prefs_md=tmp_path / "missing.md", prefs_json=pj)
    assert loaded["hard"]["target_roles"] == ["mechatronics engineer"]
