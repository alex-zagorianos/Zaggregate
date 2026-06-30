"""Wave 2b - salary parser + geo remote/US accuracy."""
from match.scorer import salary_from_text
from geo.filter import _is_remote, _remote_region_ok


def test_stipend_not_salary():
    assert salary_from_text("A $75 monthly stipend is provided.") == (None, None)


def test_range_parsed():
    assert salary_from_text("Base salary $120,000 - $140,000 per year.") == (120000.0, 140000.0)


def test_hourly_annualized_only_with_context():
    assert salary_from_text("$60/hr") == (124800.0, None)


def test_401k_skipped():
    assert salary_from_text("401(k) match up to $5,000.") == (None, None)


def test_remote_sensing_title_is_not_remote():
    assert _is_remote("Dayton, OH", "Remote Sensing Engineer") is False


def test_plain_remote_is_remote():
    assert _is_remote("Remote", "Software Engineer") is True


def test_us_region_rejects_foreign():
    assert _remote_region_ok("remote - australia", "us") is False
    assert _remote_region_ok("remote (us)", "us") is True
