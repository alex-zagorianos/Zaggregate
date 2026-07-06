"""Unit tests for ui.setup_wizard_core.parse_salary_input(_detailed) (finding #10).

webui/api/onboarding.py's /onboarding/salary-parse route used to re-derive its
own 'kind' classification (annual/hourly/none) with a private regex duplicating
what parse_salary_input already computes and discards internally. Now
parse_salary_input_detailed exposes that classification directly, and
parse_salary_input is a thin wrapper over it. These tests pin both functions'
behavior on the exact inputs the onboarding path handles today, plus the
combined-marker edge case (an explicit 'k' suffix AND an hourly marker in the
same string) that the refactor had to preserve from the original two
independent `if` statements (as opposed to an `if/elif` chain, which would
silently drop the hourly multiplier when both fire).
"""
from ui.setup_wizard_core import parse_salary_input, parse_salary_input_detailed


def test_parse_salary_input_unchanged_signature_and_values():
    assert parse_salary_input("140k") == 140000
    assert parse_salary_input("58/hr") == 58 * 2080
    assert parse_salary_input("75") == 75 * 2080  # bare small number -> hourly
    assert parse_salary_input("") is None
    assert parse_salary_input(None) is None
    assert parse_salary_input("garbage") is None


def test_detailed_matches_plain_on_every_case():
    for text in ("140k", "58/hr", "75", "90000", "$90,000", "18/hr",
                 "$18.50 per hour", "", "nope", None, "1500"):
        annual, kind = parse_salary_input_detailed(text)
        assert annual == parse_salary_input(text)


def test_detailed_classifies_140k_as_annual():
    annual, kind = parse_salary_input_detailed("140k")
    assert (annual, kind) == (140000, "annual")


def test_detailed_classifies_58_per_hr_as_hourly():
    annual, kind = parse_salary_input_detailed("58/hr")
    assert (annual, kind) == (58 * 2080, "hourly")


def test_detailed_classifies_bare_small_number_as_hourly():
    annual, kind = parse_salary_input_detailed("75")
    assert (annual, kind) == (75 * 2080, "hourly")


def test_detailed_classifies_bare_large_number_as_annual():
    annual, kind = parse_salary_input_detailed("90000")
    assert (annual, kind) == (90000, "annual")


def test_detailed_classifies_blank_and_garbage_as_none():
    assert parse_salary_input_detailed("") == (None, "none")
    assert parse_salary_input_detailed(None) == (None, "none")
    assert parse_salary_input_detailed("nope") == (None, "none")


def test_detailed_combined_k_suffix_and_hourly_marker_applies_both():
    """'90k/hr' historically applied BOTH the k-suffix multiplier (x1000) AND the
    hourly annualization (x2080) because the original code used two independent
    `if` statements, not an if/elif chain. A naive if/elif refactor would only
    apply one -- this pins the original (arguably odd, but pre-existing) behavior."""
    annual, kind = parse_salary_input_detailed("90k/hr")
    assert annual == int(round(90 * 1000 * 2080))
    assert kind == "hourly"
    assert annual == parse_salary_input("90k/hr")
