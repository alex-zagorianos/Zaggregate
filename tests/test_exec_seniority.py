"""Executive/management seekers (e.g. a VP) must not have every relevant role
dropped by the entry-mid IC gate. rubric.build_rubric infers management intent
from the target roles the user already typed, and gate.evaluate honors it."""
from match import gate as G
from match import rubric as R


def _vp_facts():  # what facts_for produces for a "VP …" posting
    return {"seniority": "director", "role_type": "manage", "required_years": 14,
            "clearance_required": False, "restriction": None}


def test_rubric_infers_exec_intent_from_roles():
    rb = R.build_rubric(prefs={"hard": {}}, cfg={"keywords": ["VP Health Informatics"]})
    assert rb["allow_management"] is True
    assert rb["seniority_target"] == "senior-exec"
    assert rb["years_cap"] >= 20
    assert "manage" not in rb["penalty_roles"]


def test_rubric_ic_roles_keep_entry_mid_defaults():
    # Regression: an IC seeker (no exec markers) is completely unchanged.
    rb = R.build_rubric(prefs={"hard": {}}, cfg={"keywords": ["controls engineer"]})
    assert rb["allow_management"] is False
    assert rb["seniority_target"] == "entry-mid"
    assert rb["years_cap"] == 8
    assert "manage" in rb["penalty_roles"]


def test_gate_keeps_vp_roles_for_exec_seeker():
    rb = R.build_rubric(prefs={"hard": {}}, cfg={"keywords": ["VP Clinical Informatics"]})
    g = G.evaluate(_vp_facts(), rb, title="Vice President, Clinical Informatics")
    assert g["decision"] != "drop", g

def test_gate_drops_vp_roles_for_ic_seeker():
    rb = R.build_rubric(prefs={"hard": {}}, cfg={"keywords": ["controls engineer"]})
    g = G.evaluate(_vp_facts(), rb, title="Vice President, Clinical Informatics")
    assert g["decision"] == "drop"
    assert "people-management role" in g["reasons"]


def test_explicit_cfg_overrides_inference():
    # A user can force IC behavior even with an exec-sounding role, and vice versa.
    rb = R.build_rubric(prefs={"hard": {}},
                        cfg={"keywords": ["VP Eng"], "allow_management": False})
    assert rb["allow_management"] is False


def test_various_exec_titles_detected():
    for kw in ["Director of Analytics", "Chief Medical Information Officer",
               "Head of Data", "Engineering Manager", "SVP Operations"]:
        rb = R.build_rubric(prefs={"hard": {}}, cfg={"keywords": [kw]})
        assert rb["allow_management"] is True, kw
