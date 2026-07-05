"""outreach.py — the BYO-AI warm-path prompt builder (B4)."""
import outreach


_EXPERIENCE = """\
# Experience

## EDUCATION
B.S. Mechanical Engineering, State Polytechnic University, 2018

## WORK EXPERIENCE
Controls Engineer, Globex Corporation, 2019-2023
Robotics Intern, Initech, 2018
"""

_JOB = {
    "title": "Senior Controls Engineer",
    "company": "Acme Robotics",
    "location": "Cincinnati, OH",
    "description": "Design and commission PLC-based automation cells. " * 80,
}

_CONTACTS = [
    {"name": "Jane Doe", "position": "Staff Engineer", "company": "Acme Robotics"},
    {"name": "John Roe", "position": "Recruiter", "company": "Acme Robotics"},
]


def test_prompt_includes_job_contacts_schools_and_employers():
    prompt = outreach.build_warm_path_prompt(
        _JOB, _CONTACTS, _EXPERIENCE, {"location": "Cincinnati, OH"})
    assert "Senior Controls Engineer" in prompt
    assert "Acme Robotics" in prompt
    assert "Jane Doe" in prompt and "Staff Engineer" in prompt
    # Schools + employers mined from experience.md.
    assert "State Polytechnic University" in prompt
    assert "Globex Corporation" in prompt
    # The four required asks are all present in the output contract.
    assert "Warm paths, ranked" in prompt
    assert "LinkedIn search strings" in prompt
    assert "INFORMATIONAL-INTERVIEW ask" in prompt
    assert "REFERRAL ask" in prompt
    assert "one polite follow-up" in prompt.lower() or "one follow-up" in prompt.lower()
    assert "120 words" in prompt


def test_prompt_survives_no_contacts_and_no_experience():
    prompt = outreach.build_warm_path_prompt(
        {"title": "PM", "company": "Globex"}, [], "", None)
    # Still a usable prompt asking for indirect paths.
    assert "none in my imported network" in prompt.lower()
    assert "Warm paths, ranked" in prompt
    assert "Globex" in prompt


def test_description_is_truncated():
    prompt = outreach.build_warm_path_prompt(_JOB, _CONTACTS, _EXPERIENCE, {})
    # The 80x-repeated description is clamped well under its raw length.
    assert len(prompt) < 12000


def test_missing_title_company_have_safe_fallbacks():
    prompt = outreach.build_warm_path_prompt({}, [], "", {})
    assert "this role" in prompt
    assert "the company" in prompt
