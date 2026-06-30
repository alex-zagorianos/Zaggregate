"""Pins JobResult.identity_key + normalize_url cross-source dedup behavior."""
from models import JobResult, normalize_url


def _job(**kw):
    base = dict(
        title="Controls Engineer",
        company="Acme",
        location="Cincinnati, OH",
        salary_min=None,
        salary_max=None,
        description="",
        url="",
        source_keyword="controls engineer",
        created="2026-06-16",
    )
    base.update(kw)
    return JobResult(**base)


def test_normalize_strips_tracking_params():
    clean = normalize_url("https://Jobs.Example.com/p/123?utm_source=x&utm_campaign=y")
    assert clean == "jobs.example.com/p/123"


def test_normalize_keeps_identity_param_gh_jid():
    out = normalize_url("https://boards.greenhouse.io/acme/jobs/9?gh_jid=9&utm_medium=z")
    assert "gh_jid=9" in out
    assert "utm_medium" not in out


def test_normalize_drops_scheme_fragment_and_trailing_slash():
    a = normalize_url("https://example.com/job/1/#apply")
    b = normalize_url("http://example.com/job/1")
    assert a == b == "example.com/job/1"


def test_normalize_falsy_returns_empty():
    assert normalize_url("") == ""
    assert normalize_url(None) == ""


def test_same_url_different_location_collides():
    url = "https://example.com/job/42?utm_source=indeed"
    a = _job(url=url, location="Cincinnati, OH")
    b = _job(url=url, location="Remote - US")
    assert a.identity_key == b.identity_key


def test_distinct_urls_do_not_collide():
    a = _job(url="https://example.com/job/1")
    b = _job(url="https://example.com/job/2")
    assert a.identity_key != b.identity_key


def test_no_url_falls_back_to_title_company_without_location():
    a = _job(url="", location="Cincinnati, OH")
    b = _job(url="", location="Dayton, OH")
    # location excluded from the fallback key -> these collide
    assert a.identity_key == b.identity_key


def test_no_url_different_company_does_not_collide():
    a = _job(url="", company="Acme")
    b = _job(url="", company="Globex")
    assert a.identity_key != b.identity_key
