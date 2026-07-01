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


# ── item 9: senior (non-exec) years cap 8 -> 15 ──────────────────────────────
def test_years_cap_default_for_plain_ic():
    rb = R.build_rubric({"profile_md": "", "hard": {}},
                        {"keywords": ["controls engineer"]})
    assert rb["years_cap"] == 8


def test_years_cap_15_for_senior_non_exec():
    rb = R.build_rubric({"profile_md": "", "hard": {}},
                        {"keywords": ["senior controls engineer", "staff embedded engineer"]})
    assert rb["years_cap"] == 15          # senior tier: 10+ yr postings still reach AI
    assert rb["allow_management"] is False  # still not an exec


def test_years_cap_25_for_exec_overrides_senior():
    rb = R.build_rubric({"profile_md": "", "hard": {}},
                        {"keywords": ["Senior Director of Engineering"]})
    assert rb["years_cap"] == 25


def test_years_cap_explicit_config_wins():
    rb = R.build_rubric({"profile_md": "", "hard": {}},
                        {"keywords": ["senior controls engineer"], "years_cap": 12})
    assert rb["years_cap"] == 12


# ── item 10: field-aware penalty_roles ───────────────────────────────────────
def test_penalty_roles_default_unchanged_for_eng():
    rb = R.build_rubric({"profile_md": "", "hard": {}},
                        {"keywords": ["controls engineer"]})
    assert rb["penalty_roles"] == ["sales", "maintain", "manage"]


def test_penalty_roles_drop_maintain_for_maintenance_field():
    # SOC 49 (maintenance/repair) -> "maintain" is this field's core work, dropped.
    rb = R.build_rubric({"profile_md": "", "hard": {}},
                        {"keywords": ["maintenance technician"],
                         "onet_soc_code": "49-9071.00"})
    assert "maintain" not in rb["penalty_roles"]
    assert "sales" in rb["penalty_roles"] and "manage" in rb["penalty_roles"]


def test_penalty_roles_drop_sales_for_sales_field():
    rb = R.build_rubric({"profile_md": "", "hard": {}},
                        {"keywords": ["sales representative"],
                         "onet_soc_code": "41-4012.00"})
    assert "sales" not in rb["penalty_roles"]
