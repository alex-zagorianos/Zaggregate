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
