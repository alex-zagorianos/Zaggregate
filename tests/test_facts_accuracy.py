"""Wave 2a - match/facts.py extraction accuracy regressions."""
from types import SimpleNamespace
from match.facts import extract_facts


def _job(title="", desc="", location="", salary_min=None, salary_max=None):
    return SimpleNamespace(title=title, description=desc, location=location,
                           salary_min=salary_min, salary_max=salary_max)


def test_clearance_negation_not_required():
    assert extract_facts(_job("Controls Engineer",
                              "No security clearance required for this role."))["clearance_required"] is False
    assert extract_facts(_job("Controls Engineer",
                              "Ability to obtain a security clearance is a plus."))["clearance_required"] is False


def test_clearance_affirmative_required():
    assert extract_facts(_job("Systems Engineer",
                              "Active TS/SCI clearance required."))["clearance_required"] is True


def test_company_tenure_is_not_required_years():
    f = extract_facts(_job("Controls Engineer",
                           "We have over 25 years in business serving the Midwest."))
    assert f["required_years"] is None


def test_experience_years_detected():
    assert extract_facts(_job("Controls Engineer",
                              "Requires 8+ years of experience in PLC programming."))["required_years"] == 8


def test_manager_title_is_manage_role():
    assert extract_facts(_job("Engineering Manager",
                              "Design and develop and build control systems."))["role_type"] == "manage"
