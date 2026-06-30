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


def test_preferences_paths_root_fallback(tmp_base):
    pj, pm = workspace.preferences_paths()
    assert pj == tmp_base / "preferences.json"
    assert pm == tmp_base / "preferences.md"


def test_preferences_paths_follow_active_project(tmp_base):
    slug = workspace.create_project("Controls", make_active=True)
    pj, pm = workspace.preferences_paths()
    # preferences now live beside that project's config.json / experience.md,
    # so they never desync from it.
    assert pj == tmp_base / "projects" / slug / "preferences.json"
    assert pm.parent == workspace.config_path().parent


# ── Item 3: first-project migration ──────────────────────────────────────────

def test_first_create_registers_default_and_new(tmp_base):
    """First create_project must register BOTH 'default' (root) and the new slug."""
    # Simulate a pre-existing root inbox
    (tmp_base / "tracker.db").write_text("existing", encoding="utf-8")

    slug = workspace.create_project("Foo", make_active=True)
    projs = workspace.list_projects()
    slugs = [p["slug"] for p in projs]
    assert "default" in slugs, "root must be registered as 'default'"
    assert slug in slugs, "new project must be registered"
    assert len(projs) == 2


def test_default_project_resolves_to_root(tmp_base):
    """After first-project migration, 'default' paths point at the ROOT, not
    projects/default/, so the pre-existing tracker.db is reachable."""
    (tmp_base / "tracker.db").write_text("root db", encoding="utf-8")
    (tmp_base / "user_config.json").write_text('{"k": 1}', encoding="utf-8")

    workspace.create_project("Bar", make_active=True)

    # root tracker.db accessible via "default"
    assert workspace.db_path("default") == tmp_base / "tracker.db"
    assert workspace.db_path("default").read_text(encoding="utf-8") == "root db"

    # root config accessible via "default"
    assert workspace.config_path("default") == tmp_base / "user_config.json"
    assert workspace.load_config("default")["k"] == 1

    # root experience.md accessible via "default"
    assert workspace.experience_file("default") == tmp_base / "experience.md"

    # new project does NOT collide with root
    assert workspace.db_path("bar") == tmp_base / "projects" / "bar" / "tracker.db"


def test_second_create_does_not_duplicate_default(tmp_base):
    """Calling create_project a second time must not add a second 'default' entry."""
    workspace.create_project("Alpha", make_active=True)
    workspace.create_project("Beta")
    slugs = [p["slug"] for p in workspace.list_projects()]
    assert slugs.count("default") == 1


def test_none_active_slug_does_not_crash_create(tmp_base):
    """create_project must not crash when called with copy_resume_from=None
    (which happens when active_slug() is None before the first project)."""
    assert workspace.active_slug() is None
    slug = workspace.create_project("Safe", make_active=True, copy_resume_from=None)
    assert slug == "safe"
    assert workspace.active_slug() == "safe"
