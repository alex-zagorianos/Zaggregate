"""Plan 3 GOAL 1 (1A/1D) — wizard writes industry + level; non-eng persona has no
eng leak; has_industry gates the discovery hint. Pure functions only (no Tk)."""
from ui import setup_wizard as W


def test_search_config_writes_industry_and_level():
    cfg = W._search_config({"roles": ["registered nurse"], "location": "Cincinnati",
                            "industry": "health_informatics", "level": "Manager/Exec"})
    assert cfg["keywords"] == ["registered nurse"]
    assert cfg["industry"] == "health_informatics"
    assert cfg["allow_management"] is True
    assert cfg["seniority_target"] == "senior-exec"
    assert cfg["years_cap"] == 25


def test_level_translations():
    assert W._level_to_config("Entry") == {"seniority_target": "entry",
                                           "allow_intern": True, "years_cap": 3}
    assert W._level_to_config("Senior")["seniority_target"] == "senior"
    assert W._level_to_config("") == {}                      # unset -> no keys


def test_blank_industry_level_is_byte_identical():
    ans = {"roles": ["controls engineer"], "location": "Cincinnati", "salary_min": 90000}
    cfg = W._search_config(ans)
    assert "industry" not in cfg and "allow_management" not in cfg
    assert "seniority_target" not in cfg                     # Alex path unchanged


def test_prefill_reads_back_industry_and_level():
    cfg = {"industry": "nursing", "allow_management": True}
    out = W.prefill_from_existing(prefs={"hard": {}}, cfg=cfg)
    assert out["industry"] == "nursing"
    assert out["level"] == "Manager/Exec"


def test_config_to_level_roundtrip():
    assert W._config_to_level({"seniority_target": "entry"}) == "Entry"
    assert W._config_to_level({"seniority_target": "senior-exec"}) == "Manager/Exec"
    assert W._config_to_level({}) == ""


def test_has_industry_gates_discovery(tmp_path):
    import json
    from scrape.company_registry import has_industry
    cj = tmp_path / "companies.json"
    cj.write_text(json.dumps({"companies": [
        {"name": "HealthCo", "ats_type": "greenhouse", "slug": "h",
         "industries": ["health_informatics"]}]}), encoding="utf-8")
    assert has_industry("health_informatics", user_json=cj) is True
    assert has_industry("underwater_basket_weaving", user_json=cj) is False
    assert has_industry("", user_json=cj) is True            # empty -> whole registry
