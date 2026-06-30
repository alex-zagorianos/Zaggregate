"""First-run Setup wizard: the pure answers->contract transform, the on-disk
apply, and the onboarding marker."""
import json

import pytest

import config
import workspace
from ui import setup_wizard as sw


def test_build_preferences_shape():
    out = sw.build_preferences({
        "roles": ["controls engineer", " plc "],
        "location": "Cincinnati",
        "remote_ok": True,
        "salary_min": 90000,
        "about": "I love automation.",
    })
    hard = out["hard"]
    assert hard["target_roles"] == ["controls engineer", "plc"]   # trimmed
    assert hard["locations"] == ["Cincinnati"]
    assert hard["salary_min"] == 90000
    assert hard["remote_ok"] is True
    # md is a plain-English profile that mentions the user's inputs
    md = out["profile_md"]
    assert "controls engineer" in md
    assert "Cincinnati" in md
    assert "90,000" in md
    assert "I love automation." in md


def test_build_preferences_empty_is_permissive():
    out = sw.build_preferences({"roles": [], "location": "", "salary_min": None})
    hard = out["hard"]
    assert hard["target_roles"] == []
    assert hard["locations"] == []
    assert hard["salary_min"] is None
    assert hard["remote_ok"] is True   # default: keep remote postings


def test_search_config_preserves_existing():
    cfg = sw._search_config(
        {"roles": ["a", "b"], "location": "Remote", "salary_min": 50000},
        existing={"industry": "manufacturing", "keywords": ["old"]})
    assert cfg["industry"] == "manufacturing"   # preserved
    assert cfg["keywords"] == ["a", "b"]          # overwritten from roles
    assert cfg["location"] == "Remote"
    assert cfg["salary_min"] == 50000


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "USER_DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "PREFERENCES_JSON", tmp_path / "preferences.json")
    monkeypatch.setattr(config, "PREFERENCES_MD", tmp_path / "preferences.md")
    monkeypatch.setattr(workspace, "BASE_DIR", tmp_path)
    return tmp_path


def test_marker_roundtrip(isolated):
    assert sw.is_onboarded() is False
    sw.mark_onboarded()
    assert sw.is_onboarded() is True


def test_apply_writes_full_contract(isolated):
    sw.apply({
        "roles": ["controls engineer"],
        "location": "Cincinnati",
        "remote_ok": False,
        "salary_min": 80000,
        "resume_text": "# Experience\n\nBuilt machines.",
        "about": "",
    })
    hard = json.loads(config.PREFERENCES_JSON.read_text(encoding="utf-8"))
    assert hard["target_roles"] == ["controls engineer"]
    assert hard["remote_ok"] is False
    assert "controls engineer" in config.PREFERENCES_MD.read_text(encoding="utf-8")
    assert workspace.load_config()["keywords"] == ["controls engineer"]
    assert "Built machines." in workspace.experience_file().read_text(encoding="utf-8")
    assert sw.is_onboarded() is True


def test_apply_without_resume_keeps_experience_untouched(isolated):
    workspace.experience_file().write_text("ORIGINAL", encoding="utf-8")
    sw.apply({"roles": ["x"], "location": "", "salary_min": None,
              "resume_text": "   ", "about": ""})   # blank resume
    assert workspace.experience_file().read_text(encoding="utf-8") == "ORIGINAL"


def test_apply_writes_about_narrative(isolated):
    # The 'about' free-text is the most valuable AI-ranking input; the wizard
    # collects it and it must land in the profile the AI reads.
    sw.apply({"roles": ["controls engineer"], "location": "", "salary_min": None,
              "resume_text": "", "about": "I love motion control; avoid pure IT."})
    md = config.PREFERENCES_MD.read_text(encoding="utf-8")
    assert "About me" in md
    assert "I love motion control; avoid pure IT." in md


def test_apply_colocates_preferences_with_active_project(isolated):
    # Once projects exist, apply() must write preferences BESIDE the active
    # project (not the root) so they don't desync from its config/resume, and
    # preferences.load() must read them back from there.
    import preferences
    slug = workspace.create_project("Controls", make_active=True)
    sw.apply({"roles": ["plc engineer"], "location": "Cincinnati",
              "salary_min": 95000, "resume_text": "", "about": "automation"})
    pj, _ = workspace.preferences_paths()
    assert slug in str(pj) and pj.exists()
    assert not config.PREFERENCES_JSON.exists()      # nothing stranded at root
    loaded = preferences.load()                      # bare -> active project
    assert loaded["hard"]["target_roles"] == ["plc engineer"]
    assert "automation" in loaded["profile_md"]


# ── Item 4: wizard pre-populate ───────────────────────────────────────────────

def test_prefill_from_existing_uses_prefs_and_cfg():
    """prefill_from_existing() correctly reads roles/location/salary/about
    from the preferences dict and the search-config dict (pure, no I/O)."""
    prefs = {
        "hard": {
            "target_roles": ["controls engineer", "plc programmer"],
            "locations": ["Cincinnati, OH"],
            "remote_ok": False,
            "salary_min": 95000,
        },
        "profile_md": (
            "# My Job Preferences\n\n"
            "Target roles / keywords: controls engineer\n\n"
            "## About me / what I'm looking for\n\n"
            "I love motion control and automation.\n"
        ),
    }
    cfg = {"keywords": ["old keyword"], "location": "Columbus"}
    out = sw.prefill_from_existing(prefs=prefs, cfg=cfg)
    # roles come from hard.target_roles (not cfg.keywords)
    assert "controls engineer" in out["roles"]
    assert "plc programmer" in out["roles"]
    # location comes from hard.locations[0]
    assert out["location"] == "Cincinnati, OH"
    # remote_ok
    assert out["remote_ok"] is False
    # salary_min as string
    assert out["salary_min"] == "95000"
    # about extracted from profile_md
    assert "I love motion control" in out["about"]


def test_prefill_falls_back_to_cfg_when_no_hard_roles():
    """When hard.target_roles is empty, prefill falls back to cfg.keywords."""
    prefs = {"hard": {"target_roles": [], "locations": [], "remote_ok": True,
                      "salary_min": None}, "profile_md": ""}
    cfg = {"keywords": ["mechanical engineer"], "location": "Remote"}
    out = sw.prefill_from_existing(prefs=prefs, cfg=cfg)
    assert "mechanical engineer" in out["roles"]
    assert out["location"] == "Remote"


def test_prefill_empty_when_nothing_configured():
    """prefill with no data returns safe empty defaults."""
    out = sw.prefill_from_existing(prefs={}, cfg={})
    assert out["roles"] == ""
    assert out["location"] == ""
    assert out["remote_ok"] is True
    assert out["salary_min"] == ""
    assert out["about"] == ""


def test_prefill_about_not_contaminated_by_other_sections():
    """The 'about' extraction stops after the marker; other md sections are not
    included (they would confuse the user seeing a long pre-filled block)."""
    prefs = {
        "hard": {},
        "profile_md": (
            "# Prefs\n\n"
            "Target roles: foo\n\n"
            "## About me / what I'm looking for\n\n"
            "Just the about text here.\n"
        ),
    }
    out = sw.prefill_from_existing(prefs=prefs, cfg={})
    assert "Just the about text here." in out["about"]
    assert "Target roles" not in out["about"]
