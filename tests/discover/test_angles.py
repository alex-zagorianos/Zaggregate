"""P2 — industry-derived enumeration angles + industry resolution.

Byte-identical BC guarantee: empty or eng-like industry -> DEFAULT_ANGLES, so
Alex's controls flow is unchanged; any other field -> neutral angles naming it.
"""
import enumerate_companies as ec
from discover import enumerate as enum


def test_empty_industry_is_default_angles_byte_identical():
    assert enum.angles_for_industry("") == enum.DEFAULT_ANGLES
    assert enum.angles_for_industry(None) == enum.DEFAULT_ANGLES


def test_eng_like_industries_stay_default_angles():
    for ind in ("controls_engineering", "software", "robotics", "applied-ai",
                "mechanical", "embedded"):
        assert enum.angles_for_industry(ind) == enum.DEFAULT_ANGLES, ind


def test_non_eng_industry_gets_neutral_field_named_angles():
    angles = enum.angles_for_industry("health_informatics")
    assert angles != enum.DEFAULT_ANGLES
    assert angles[0] == ""                       # generic angle preserved
    joined = " ".join(angles).lower()
    assert "health informatics" in joined        # names the field
    assert "controls" not in joined              # no eng leak
    assert "robotics" not in joined


def test_national_scope_angle_set():
    metro = enum.angles_for_industry("health_informatics", scope="metro")
    national = enum.angles_for_industry("health_informatics", scope="national")
    assert national != metro
    joined = " ".join(national).lower()
    assert "nationwide" in joined or "remote" in joined


def test_is_eng_like_and_humanize():
    assert enum.is_eng_like("controls_engineering")
    assert not enum.is_eng_like("health_informatics")
    assert enum.humanize_industry("health_informatics") == "health informatics"
    assert enum.humanize_industry("", keywords=["nurse manager"]) == "nurse manager"


def test_resolve_industry_precedence(monkeypatch):
    # CLI arg wins outright.
    assert ec._resolve_industry("nursing") == "nursing"

    # No arg -> falls through to active-project config, else DEFAULT_INDUSTRY.
    import config
    monkeypatch.setattr(config, "DEFAULT_INDUSTRY", "", raising=False)
    import workspace
    monkeypatch.setattr(workspace, "load_config", lambda *a, **k: {"industry": "legal"})
    assert ec._resolve_industry(None) == "legal"

    monkeypatch.setattr(workspace, "load_config", lambda *a, **k: {})
    monkeypatch.setattr(config, "DEFAULT_INDUSTRY", "finance", raising=False)
    assert ec._resolve_industry(None) == "finance"
