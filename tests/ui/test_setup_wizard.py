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
