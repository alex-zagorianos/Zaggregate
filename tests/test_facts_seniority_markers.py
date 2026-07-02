"""S32 detector extensions in match/facts.py: Roman IV and bare '8+ YOE' /
'8+ years of experience'. Additive -- previously-detected strings are unchanged.
"""
from match import facts


def test_roman_iv_detected_as_senior():
    assert facts._detect_seniority("Software Engineer IV", "") == "senior"


def test_roman_i_ii_iii_unchanged():
    assert facts._detect_seniority("Systems Engineer I", "") == "entry"
    assert facts._detect_seniority("Engineer II", "") == "mid"
    assert facts._detect_seniority("Controls Engineer III", "") == "senior"


def test_yoe_forms_detected():
    assert facts._detect_required_years("8+ YOE") == 8
    assert facts._detect_required_years("8+ years of experience") == 8
    assert facts._detect_required_years("requires 10 years of experience") == 10


def test_existing_years_forms_unchanged():
    # The pre-S32 leading-qualifier form still works.
    assert facts._detect_required_years("minimum of 8 years required") == 8
    assert facts._detect_required_years("3+ years experience preferred") == 3
    # Company tenure (no experience qualifier) is still NOT a requirement.
    assert facts._detect_required_years("proudly serving for over 25 years") is None
