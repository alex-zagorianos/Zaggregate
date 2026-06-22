import json
from discover.registry import merge_discovered

def test_merge_adds_new_boards(tmp_path):
    p = tmp_path / "companies.json"
    n = merge_discovered({"greenhouse": {"acme", "beta"}, "lever": {"gamma"}}, p)
    assert n == 3
    saved = json.loads(p.read_text(encoding="utf-8"))["companies"]
    slugs = {c["slug"] for c in saved}
    assert {"acme", "beta", "gamma"} <= slugs

def test_user_wins_existing_not_overwritten(tmp_path):
    p = tmp_path / "companies.json"
    p.write_text(json.dumps({"_comment": "mine", "companies": [
        {"name": "Acme", "ats_type": "greenhouse", "slug": "acme", "industries": ["mine"]}]}),
        encoding="utf-8")
    n = merge_discovered({"greenhouse": {"acme", "beta"}}, p)
    assert n == 1  # acme already present (user wins), only beta added
    raw = json.loads(p.read_text(encoding="utf-8"))
    assert raw["_comment"] == "mine"
    acme = [c for c in raw["companies"] if c["slug"] == "acme"][0]
    assert acme["industries"] == ["mine"]

def test_empty_boards_logs_and_returns_zero(tmp_path, capsys):
    p = tmp_path / "companies.json"
    n = merge_discovered({}, p)
    assert n == 0
    assert "WARNING" in capsys.readouterr().out
