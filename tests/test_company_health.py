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


def test_browser_only_boards_are_never_probed_or_pruned(tmp_path):
    """S34 review follow-up: a browser-only board (walled tenant / clipped
    direct page) is by definition unreadable server-side — probing it is a
    guaranteed fail-streak that would DELETE a board the user explicitly
    browser-verified, and for a clipped direct slug the probe would issue the
    very server-side fetch we promise never to make. prune_companies must skip
    them: never probed, never penalized, never removed."""
    cj, hp = tmp_path / "companies.json", tmp_path / "health.json"
    cj.write_text(json.dumps({
        "companies": [
            {"name": "Walled Co", "ats_type": "workday_cxs", "slug": "walled:1:X",
             "industries": [], "extra": {"browser_only": True}},
            {"name": "Clipped Direct", "ats_type": "direct",
             "slug": "https://careers.walled.example/jobs",
             "industries": [], "extra": {"browser_only": True}},
            {"name": "Dead Co", "ats_type": "greenhouse", "slug": "deadco",
             "industries": []},
        ],
    }), encoding="utf-8")

    probed = []
    def probe(e):
        probed.append(e.slug)
        return False                       # everything probed looks dead

    # Even at threshold=1 (immediate removal for real dead boards), the
    # browser-only entries survive and were never even probed.
    removed = prune_companies(threshold=1, json_path=cj, health_path=hp,
                              probe=probe)
    assert removed == ["Dead Co"]
    assert probed == ["deadco"]            # only the normal entry was probed
    left = {c["name"] for c in json.loads(cj.read_text(encoding="utf-8"))["companies"]}
    assert left == {"Walled Co", "Clipped Direct"}
