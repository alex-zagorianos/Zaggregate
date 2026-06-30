"""New projects must seed a parseable, identity-neutral experience.md (2026-06)."""
import workspace


def test_new_project_seeds_parseable_stub(tmp_path, monkeypatch):
    monkeypatch.setattr(workspace, "BASE_DIR", tmp_path)
    slug = workspace.create_project("Test Campaign")
    text = (tmp_path / "projects" / slug / "experience.md").read_text(encoding="utf-8")
    for h in ("## CONTACT", "## EDUCATION", "## TECHNICAL SKILLS",
              "## WORK EXPERIENCE", "## NOTES FOR RESUME GENERATION"):
        assert h in text
    assert "Alex Zagorianos" not in text


def test_new_project_resume_copy_is_opt_in(tmp_path, monkeypatch):
    """C1 recurrence guard: a new project created WITHOUT an explicit copy source
    must NOT inherit another project's resume — it gets the neutral stub. (The GUI
    now makes resume-copy opt-in so a campaign for someone else can't silently
    ship the wrong person's experience.md.) Explicit opt-in copy still works."""
    monkeypatch.setattr(workspace, "BASE_DIR", tmp_path)
    owner = workspace.create_project("Owner")
    (tmp_path / "projects" / owner / "experience.md").write_text(
        "# Experience\n\n## CONTACT\n- Name: Jane Doe\n", encoding="utf-8")

    # Default (no copy source) -> stub, NOT Jane's resume.
    other = workspace.create_project("Someone Else")
    other_text = (tmp_path / "projects" / other / "experience.md").read_text(encoding="utf-8")
    assert "Jane Doe" not in other_text
    assert "## CONTACT" in other_text

    # Opt-in copy still works when explicitly requested.
    cloned = workspace.create_project("My Clone", copy_resume_from=owner)
    cloned_text = (tmp_path / "projects" / cloned / "experience.md").read_text(encoding="utf-8")
    assert "Jane Doe" in cloned_text
