"""Workspace path resolution: root fallback pre-migration, per-project after."""
import pytest

import workspace


@pytest.fixture
def tmp_base(tmp_path, monkeypatch):
    monkeypatch.setattr(workspace, "BASE_DIR", tmp_path)
    return tmp_path


def test_root_fallback_when_no_projects(tmp_base):
    assert not workspace.has_projects()
    assert workspace.db_path() == tmp_base / "tracker.db"
    assert workspace.experience_file() == tmp_base / "experience.md"
    assert workspace.config_path() == tmp_base / "user_config.json"
    assert workspace.active_slug() is None


def test_create_project_and_resolve(tmp_base):
    slug = workspace.create_project("Controls — Cincinnati",
                                    config={"location": "Cincinnati"}, make_active=True)
    assert slug == "controls-cincinnati"
    assert workspace.has_projects()
    assert workspace.active_slug() == slug
    assert workspace.db_path() == tmp_base / "projects" / slug / "tracker.db"
    assert workspace.load_config()["location"] == "Cincinnati"
    assert workspace.experience_file().exists()


def test_switch_active(tmp_base):
    a = workspace.create_project("Project A", make_active=True)
    b = workspace.create_project("Project B")
    assert workspace.active_slug() == a       # first stays active
    workspace.set_active(b)
    assert workspace.active_slug() == b
    assert workspace.db_path().parent.name == b


def test_set_active_unknown_raises(tmp_base):
    workspace.create_project("Only", make_active=True)
    with pytest.raises(ValueError):
        workspace.set_active("nope")


def test_copy_resume_from_path(tmp_base):
    seed = tmp_base / "seed_experience.md"
    seed.write_text("# Seed Resume\n", encoding="utf-8")
    workspace.create_project("With Resume", copy_resume_from=seed, make_active=True)
    assert "Seed Resume" in workspace.experience_file().read_text(encoding="utf-8")
