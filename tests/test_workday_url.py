"""Workday job-URL construction.

The CXS jobs endpoint returns externalPath as site-relative ("/job/...") with no
site segment, so host+externalPath 404s. The public URL must include the site
(e.g. ".../CaterpillarCareers/job/..."). Regression test for the Caterpillar
broken-link bug.
"""
from scrape.workday_scraper import _job_url

HOST = "https://cat.wd5.myworkdayjobs.com"


def test_inserts_site_segment_for_site_relative_path():
    url = _job_url("cat", "5", "CaterpillarCareers",
                   "/job/Seguin-Texas/Controls-Engineer_R0000373539")
    assert url == HOST + "/CaterpillarCareers/job/Seguin-Texas/Controls-Engineer_R0000373539"


def test_does_not_double_insert_when_site_already_present():
    path = "/CaterpillarCareers/job/Seguin-Texas/Controls-Engineer_R1"
    assert _job_url("cat", "5", "CaterpillarCareers", path) == HOST + path


def test_handles_locale_prefixed_path():
    path = "/en-US/CaterpillarCareers/job/Seguin-Texas/Controls-Engineer_R1"
    assert _job_url("cat", "5", "CaterpillarCareers", path) == HOST + path


def test_empty_path_returns_empty():
    assert _job_url("cat", "5", "CaterpillarCareers", "") == ""
