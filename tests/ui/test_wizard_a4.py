"""A4 slice: wizard hourly-salary parsing and role->industry derivation. Pure
functions only (no Tk)."""
from ui import setup_wizard as sw


# -- hourly salary input (P3) ----------------------------------------------------
def test_parse_salary_annual_inputs():
    assert sw.parse_salary_input("90000") == 90000
    assert sw.parse_salary_input("$90,000") == 90000
    assert sw.parse_salary_input("90k") == 90000
    assert sw.parse_salary_input("$90K") == 90000


def test_parse_salary_hourly_inputs_annualize():
    assert sw.parse_salary_input("18/hr") == 18 * 2080
    assert sw.parse_salary_input("$18.50 per hour") == int(round(18.50 * 2080))
    assert sw.parse_salary_input("25 hr") == 25 * 2080
    assert sw.parse_salary_input("30/hour") == 30 * 2080


def test_parse_salary_bare_small_number_treated_hourly():
    # A bare small number with no unit is almost certainly an hourly wage.
    assert sw.parse_salary_input("18") == 18 * 2080


def test_parse_salary_blank_and_garbage_none():
    assert sw.parse_salary_input("") is None
    assert sw.parse_salary_input("   ") is None
    assert sw.parse_salary_input("negotiable") is None


# -- role -> industry derivation (P3) --------------------------------------------
def test_derive_industry_from_nonneg_role():
    # A nurse role resolves to a non-engineering O*NET occupation -> a field label.
    got = sw._derive_industry("", ["registered nurse"])
    assert got and "nurse" in got.lower()


def test_derive_industry_respects_explicit_field():
    # If the user already typed a field, never override it.
    assert sw._derive_industry("health informatics", ["registered nurse"]) == ""


def test_derive_industry_eng_role_is_byte_identical():
    # Engineering/tech roles must NOT get a field prefilled (Alex path unchanged).
    assert sw._derive_industry("", ["controls engineer"]) == ""
    assert sw._derive_industry("", ["software engineer"]) == ""


def test_derive_industry_unresolvable_role_stays_blank():
    assert sw._derive_industry("", ["underwater basket weaver"]) == ""


def test_derive_industry_first_resolving_role_wins():
    got = sw._derive_industry("", ["controls engineer", "staff accountant"])
    assert got and ("accountant" in got.lower() or "auditor" in got.lower())
