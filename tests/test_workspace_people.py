"""Plan 3 GOAL 2 — a person is a set of projects; person metadata on the registry
+ ranking automatically follows the active person (2A/2C/2D)."""
import workspace


def _fresh(tmp_path, monkeypatch):
    monkeypatch.setattr(workspace, "BASE_DIR", tmp_path)


def test_create_project_stores_person_and_queries(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    # First real project auto-registers root 'default' (person=None, unassigned).
    workspace.create_project("Dad Health IT", person="Dad", today="2026-06-30")
    workspace.create_project("Dad Remote", person="Dad", today="2026-06-30")
    workspace.create_project("Alex Controls", today="2026-06-30")  # unassigned

    ppl = workspace.people()
    assert None in ppl and "Dad" in ppl              # None = default/root + Alex
    dad = [p["name"] for p in workspace.projects_for_person("Dad")]
    assert dad == ["Dad Health IT", "Dad Remote"]
    unassigned = {p["name"] for p in workspace.projects_for_person(None)}
    assert "Default" in unassigned and "Alex Controls" in unassigned


def test_person_of_active(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    slug = workspace.create_project("Mom Nursing", person="Mom", make_active=True,
                                    today="2026-06-30")
    assert workspace.person_of() == "Mom"
    assert workspace.person_of(slug) == "Mom"


def test_old_entries_without_person_are_none(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    workspace.create_project("Legacy", today="2026-06-30")   # no person kwarg
    entry = [p for p in workspace.list_projects() if p["name"] == "Legacy"][0]
    assert "person" not in entry                     # omitted, back-compat
    assert workspace.person_of(entry["slug"]) is None


def test_ranking_follows_active_person_profile(tmp_path, monkeypatch):
    """2C: config + experience resolve to the ACTIVE project, so switching person
    switches whose profile ranks jobs — no extra plumbing."""
    _fresh(tmp_path, monkeypatch)
    dad = workspace.create_project("Dad", person="Dad", make_active=True,
                                   config={"industry": "health_informatics"},
                                   today="2026-06-30")
    alex = workspace.create_project("Alex", config={"industry": "controls_engineering"},
                                    today="2026-06-30")

    workspace.experience_file(dad).write_text("# Dad\nClinical informatics.", encoding="utf-8")
    workspace.experience_file(alex).write_text("# Alex\nPLC and controls.", encoding="utf-8")

    workspace.set_active(dad)
    assert workspace.load_config()["industry"] == "health_informatics"
    assert "informatics" in workspace.experience_file().read_text(encoding="utf-8").lower()

    workspace.set_active(alex)
    assert workspace.load_config()["industry"] == "controls_engineering"
    assert "controls" in workspace.experience_file().read_text(encoding="utf-8").lower()
