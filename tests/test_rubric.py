from match import rubric as R


def test_build_rubric_from_sources():
    prefs = {"profile_md": "I want controls + embedded build roles.",
             "hard": {"salary_min": None, "dealbreakers": ["sales engineer"]}}
    cfg = {"keywords": ["controls engineer", "embedded systems engineer"],
           "salary_min": 85000, "exclude_titles": ["ai", "machine learning"]}
    rb = R.build_rubric(prefs, cfg)
    assert rb["comp_floor"] == 85000
    assert rb["target_roles"][0] == "controls engineer"
    assert "ai" in rb["hard_no_titles"] and "sales engineer" in rb["hard_no_titles"]
    assert rb["allow_intern"] is False and rb["has_clearance"] is False
    assert rb["profile_md"].startswith("I want controls")


def test_rubric_text_renders_criteria_and_profile():
    rb = R.build_rubric(
        {"profile_md": "Build-not-maintain; real-time control.", "hard": {}},
        {"keywords": ["controls engineer"], "salary_min": 85000, "exclude_titles": ["ai"]})
    txt = R.rubric_text(rb)
    assert "controls engineer" in txt
    assert "$85,000" in txt
    assert "ai" in txt
    assert "internships" in txt          # no-intern policy surfaced
    assert "Build-not-maintain" in txt   # profile prose carried through


def test_build_rubric_tolerates_empty():
    rb = R.build_rubric({"profile_md": "", "hard": {}}, {})
    assert rb["target_roles"] == [] and rb["comp_floor"] is None
    assert isinstance(R.rubric_text(rb), str)
