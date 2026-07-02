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


# ── Item 25: persist O*NET-SOC code alongside a new project's industry ──────
def test_create_project_persists_onet_soc_for_known_industry(tmp_base):
    slug = workspace.create_project(
        "Nursing", config={"industry": "registered nurse"}, make_active=True)
    cfg = workspace.load_config(slug)
    assert cfg["onet_soc_code"] == "29-1141.00"
    assert cfg["onet_soc_title"] == "Registered Nurses"
    assert cfg["industry"] == "registered nurse"        # free text untouched


def test_create_project_no_soc_key_without_industry(tmp_base):
    slug = workspace.create_project("No Industry", config={"location": "Remote"},
                                    make_active=True)
    cfg = workspace.load_config(slug)
    assert "onet_soc_code" not in cfg
    assert "onet_soc_title" not in cfg


def test_create_project_no_soc_key_for_unresolvable_industry(tmp_base):
    slug = workspace.create_project(
        "Mystery", config={"industry": "underwater basket weaving"}, make_active=True)
    cfg = workspace.load_config(slug)
    assert "onet_soc_code" not in cfg


def test_create_project_no_config_arg_does_not_crash(tmp_base):
    # config=None (the common call shape) must not crash _attach_onet_soc.
    slug = workspace.create_project("Bare", make_active=True)
    cfg = workspace.load_config(slug)
    assert "onet_soc_code" not in cfg


def test_create_project_does_not_overwrite_existing_config(tmp_base):
    """The onet_soc enrichment must only run at CREATION (mirrors the existing
    `if not cfg_file.exists()` guard) — never touch an already-configured
    project's config.json on a second create_project call with the same slug."""
    slug = workspace.create_project("Nursing", slug="nursing",
                                    config={"industry": "registered nurse"},
                                    make_active=True)
    # Simulate the user hand-editing config.json after creation.
    cfg = workspace.load_config(slug)
    cfg["onet_soc_code"] = "EDITED"
    workspace.save_config(cfg, slug)
    # A second create_project call for the same slug (e.g. an idempotent
    # re-run) must not stomp the user's edit.
    workspace.create_project("Nursing", slug="nursing",
                             config={"industry": "registered nurse"})
    assert workspace.load_config(slug)["onet_soc_code"] == "EDITED"


# ── process-local project pin (concurrency isolation) ─────────────────────────
def test_pin_active_overrides_projects_json(tmp_base):
    """A pinned slug wins over projects.json 'active', so every path resolves to
    the pinned project even if another process rewrites 'active' mid-run."""
    a = workspace.create_project("Project A", make_active=True)
    b = workspace.create_project("Project B")
    workspace.pin_active(a)
    try:
        # Simulate a concurrent GUI switch / second run flipping the shared pointer.
        workspace.set_active(b)
        assert workspace.active_slug() == a          # pin wins, not b
        assert workspace.db_path().parent.name == a
        assert workspace.output_dir().parent.name == a
        assert workspace.config_path().parent.name == a
    finally:
        workspace.unpin_active()
    assert workspace.active_slug() == b              # unpinned -> reads disk again


def test_pin_active_none_is_noop(tmp_base):
    a = workspace.create_project("Project A", make_active=True)
    workspace.pin_active(None)
    assert workspace.active_slug() == a              # falls through to projects.json
    workspace.unpin_active()


# ── scaffold_preferences (item 2: shared preferences scaffold helper) ─────────
import json as _json


def test_create_project_scaffolds_preferences(tmp_base):
    # Persona finding: create_project seeded config + experience but NOT
    # preferences, so a programmatic/AI path hit an empty contract. It must now
    # scaffold preferences.{json,md} beside the project.
    slug = workspace.create_project("Nurse Boise", make_active=True)
    pj, pm = workspace.preferences_paths(slug)
    assert pj.exists() and pm.exists()
    hard = _json.loads(pj.read_text(encoding="utf-8"))
    # A valid, permissive default contract (matches preferences._DEFAULT_HARD).
    assert hard["remote_ok"] is True
    assert hard["target_roles"] == []
    assert hard["salary_min"] is None
    assert "My Job Preferences" in pm.read_text(encoding="utf-8")


def test_scaffolded_preferences_load_cleanly(tmp_base):
    # A freshly-scaffolded project must round-trip through preferences.load()
    # without falling back to defaults on a malformed file.
    import preferences
    slug = workspace.create_project("Data Phoenix", make_active=True)
    loaded = preferences.load()          # bare -> active project
    assert loaded["hard"]["target_roles"] == []
    assert loaded["hard"]["remote_ok"] is True


def test_scaffold_preferences_is_non_destructive(tmp_base):
    slug = workspace.create_project("Keep Me", make_active=True)
    pj, pm = workspace.preferences_paths(slug)
    pj.write_text('{"salary_min": 123456, "target_roles": ["x"]}', encoding="utf-8")
    pm.write_text("MY CUSTOM PROFILE", encoding="utf-8")
    # Default (overwrite=False, no content) must leave existing files untouched.
    workspace.scaffold_preferences(slug)
    assert _json.loads(pj.read_text(encoding="utf-8"))["salary_min"] == 123456
    assert pm.read_text(encoding="utf-8") == "MY CUSTOM PROFILE"


def test_scaffold_preferences_writes_supplied_content(tmp_base):
    slug = workspace.create_project("Marketing Remote", make_active=True)
    pj, pm = workspace.scaffold_preferences(
        slug, hard={"salary_min": 90000, "target_roles": ["seo"]},
        profile_md="# custom\n\nremote marketer")
    hard = _json.loads(pj.read_text(encoding="utf-8"))
    assert hard["salary_min"] == 90000
    assert hard["target_roles"] == ["seo"]
    # Supplied hard MERGES over the permissive defaults, so absent keys are still
    # present and permissive.
    assert hard["remote_ok"] is True
    assert hard["dealbreakers"] == []
    assert pm.read_text(encoding="utf-8") == "# custom\n\nremote marketer"


def test_scaffold_preferences_overwrite_flag(tmp_base):
    slug = workspace.create_project("Overwrite Me", make_active=True)
    pj, pm = workspace.preferences_paths(slug)
    pj.write_text('{"salary_min": 1}', encoding="utf-8")
    pm.write_text("OLD", encoding="utf-8")
    workspace.scaffold_preferences(slug, overwrite=True)
    # overwrite=True with no content resets both to the permissive default.
    assert _json.loads(pj.read_text(encoding="utf-8"))["salary_min"] is None
    assert "My Job Preferences" in pm.read_text(encoding="utf-8")
