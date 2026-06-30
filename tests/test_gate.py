from match import gate as G
from models import JobResult


def _rubric(**over):
    base = {"comp_floor": 85000, "seniority_target": "entry-mid", "years_cap": 8,
            "allow_intern": False, "has_clearance": False,
            "hard_no_titles": ["ai", "machine learning"], "penalty_roles": ["sales", "maintain", "manage"],
            "target_roles": ["controls engineer"], "profile_md": ""}
    base.update(over)
    return base


def _facts(**over):
    base = {"seniority": "mid", "required_years": None, "role_type": "build",
            "clearance_required": False, "location_type": "onsite", "restriction": None,
            "comp_min": None, "comp_max": None, "top_skills": []}
    base.update(over)
    return base


def test_clean_build_role_keeps():
    g = G.evaluate(_facts(role_type="build", seniority="entry"), _rubric(), title="Controls Engineer")
    assert g["decision"] == "keep"


def test_intern_dropped_unless_allowed():
    assert G.evaluate(_facts(seniority="intern"), _rubric())["decision"] == "drop"
    assert G.evaluate(_facts(seniority="intern"), _rubric(allow_intern=True))["decision"] != "drop"


def test_clearance_dropped_unless_candidate_has_it():
    assert G.evaluate(_facts(clearance_required=True), _rubric())["decision"] == "drop"
    assert G.evaluate(_facts(clearance_required=True), _rubric(has_clearance=True))["decision"] != "drop"


def test_people_management_dropped():
    g = G.evaluate(_facts(seniority="manager", role_type="manage"), _rubric(), title="Engineering Manager")
    assert g["decision"] == "drop" and any("management" in r for r in g["reasons"])


def test_foreign_restriction_dropped_us_kept():
    assert G.evaluate(_facts(restriction="Japan work visa required"), _rubric())["decision"] == "drop"
    assert G.evaluate(_facts(restriction="US work authorization required"), _rubric())["decision"] != "drop"


def test_excluded_title_dropped():
    g = G.evaluate(_facts(), _rubric(), title="Machine Learning Engineer")
    assert g["decision"] == "drop"


def test_years_cap_dropped():
    assert G.evaluate(_facts(required_years=10), _rubric(years_cap=8))["decision"] == "drop"
    assert G.evaluate(_facts(required_years=4), _rubric(years_cap=8))["decision"] != "drop"


def test_sales_role_downranked_not_dropped():
    g = G.evaluate(_facts(role_type="sales"), _rubric())
    assert g["decision"] == "downrank"


def test_senior_downranked():
    g = G.evaluate(_facts(seniority="senior", role_type="build"), _rubric(), title="Senior Firmware Engineer")
    assert g["decision"] == "downrank"


def test_partition_splits():
    jobs = [JobResult("Controls Engineer", "A", "Cincinnati", None, None, "", "https://x/1", "", "", "test"),
            JobResult("EE Intern", "B", "Austin", None, None, "", "https://x/2", "", "", "test")]
    pairs = [(jobs[0], _facts(seniority="entry")), (jobs[1], _facts(seniority="intern"))]
    kept, dropped = G.partition(pairs, _rubric())
    assert [j.title for j, _, _ in kept] == ["Controls Engineer"]
    assert [j.title for j, _, _ in dropped] == ["EE Intern"]
