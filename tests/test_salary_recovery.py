"""salary_from_text should recover bare comma-grouped ranges (2026-06 review)."""
from match.scorer import salary_from_text


def test_recovers_bare_comma_range():
    assert salary_from_text("Pay range: 120,000 - 150,000") == (120000.0, 150000.0)


def test_still_parses_dollar_form():
    assert salary_from_text("$130,000 to $160,000") == (130000.0, 160000.0)


def test_ignores_non_salary_numbers():
    assert salary_from_text("401(k) match up to 6%") == (None, None)
    assert salary_from_text("No pay listed") == (None, None)
