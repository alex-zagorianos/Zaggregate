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


# ── follow-up / thank-you stage selection (B5) ─────────────────────────────────

def test_followup_stage_is_followup_before_any_interview():
    assert outreach.followup_stage({"status": "interested"}) == "followup"
    assert outreach.followup_stage({"status": "applied"}) == "followup"
    # Terminal non-interview statuses are still plain follow-ups.
    assert outreach.followup_stage({"status": "rejected"}) == "followup"
    assert outreach.followup_stage({"status": "ghosted"}) == "followup"


def test_followup_stage_is_thank_you_at_interview_statuses():
    for st in ("phone_screen", "interview", "offer", "accepted"):
        assert outreach.followup_stage({"status": st}) == "thank_you"


def test_followup_stage_is_thank_you_when_a_round_exists():
    # A logged round wins even at a pre-interview status.
    row = {"status": "applied", "_rounds": [{"kind": "phone"}]}
    assert outreach.followup_stage(row) == "thank_you"
    # `rounds` (the un-prefixed key) is also honored.
    assert outreach.followup_stage(
        {"status": "applied", "rounds": [{"kind": "tech"}]}) == "thank_you"


def test_followup_prompt_followup_wording_and_rules():
    row = {"title": "Backend Engineer", "company": "Globex", "status": "applied"}
    prompt = outreach.build_followup_prompt(row)
    assert "post-application follow-up" in prompt
    assert "Globex" in prompt and "Backend Engineer" in prompt
    # Etiquette rules are embedded verbatim.
    assert "exactly ONE follow-up" in prompt
    assert "No groveling" in prompt
    assert "120 words" in prompt


def test_followup_prompt_thank_you_wording_and_rules():
    row = {"title": "Backend Engineer", "company": "Globex",
           "status": "interview",
           "_rounds": [{"kind": "onsite", "interviewer": "Dana",
                        "scheduled_at": "2026-07-01"}]}
    prompt = outreach.build_followup_prompt(row)
    assert "THANK-YOU" in prompt
    assert "within 24 hours" in prompt
    assert "120 words" in prompt
    assert "No groveling" in prompt
    # The most-recent-round context grounds the note.
    assert "onsite" in prompt and "Dana" in prompt


def test_followup_prompt_explicit_stage_overrides_selection():
    # Force a follow-up even though the status would auto-select thank-you.
    row = {"title": "PM", "company": "Acme", "status": "interview"}
    prompt = outreach.build_followup_prompt(row, "followup")
    assert "post-application follow-up" in prompt


def test_followup_prompt_safe_fallbacks():
    prompt = outreach.build_followup_prompt({})
    assert "the role" in prompt and "the company" in prompt


# ── interview prep (B5) ────────────────────────────────────────────────────────

def test_interview_prep_folds_in_experience():
    row = {"title": "Senior Controls Engineer", "company": "Acme Robotics",
           "location": "Cincinnati, OH", "description": "Commission PLC cells."}
    prompt = outreach.build_interview_prep_prompt(row, _EXPERIENCE)
    assert "Senior Controls Engineer" in prompt and "Acme Robotics" in prompt
    # The five required asks.
    assert "Likely interview areas" in prompt
    assert "Ten practice questions" in prompt
    assert "BEHAVIORAL" in prompt and "ROLE-SPECIFIC" in prompt
    assert "Strong-answer sketches from MY experience" in prompt
    assert "Questions I should ask them" in prompt
    assert "Red flags to listen for" in prompt
    # The user's real background flowed in (grounds the answers).
    assert "Globex Corporation" in prompt
    assert "State Polytechnic University" in prompt
    # The JD excerpt is present.
    assert "Commission PLC cells" in prompt


def test_interview_prep_survives_no_experience():
    prompt = outreach.build_interview_prep_prompt(
        {"title": "PM", "company": "Globex"}, "")
    assert "Ten practice questions" in prompt
    assert "Globex" in prompt


def test_interview_prep_safe_fallbacks():
    prompt = outreach.build_interview_prep_prompt({})
    assert "this role" in prompt and "the company" in prompt
