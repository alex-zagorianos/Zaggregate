"""E2 sector-feed RSS clients: parse from captured fixtures + industry gating +
self-skip. Fixtures are derived from REAL captured feed responses (HigherEdJobs
catID=148, RNJobSite /rss/jobs & /rss/jobs/type/444, both fetched 2026-07-01);
jobs.ac.uk uses a synthetic standard-RSS fixture (its live endpoint is
PROVISIONAL/unverified — see the client docstring)."""
import pytest

import industry_profile
from search.higheredjobs_client import (
    HigherEdJobsClient,
    _categories_for_industry,
    _split_company_location,
)
from search.rnjobsite_client import RNJobSiteClient, _should_poll
from search.jobsacuk_client import JobsAcUkClient, opt_in_active


@pytest.fixture(autouse=True)
def _clear_profile_cache():
    industry_profile.clear_cache()
    yield
    industry_profile.clear_cache()


def _client(cls, tmp_path, **kw):
    return cls(cache_dir=tmp_path, cache_enabled=False, **kw)


# ── HigherEdJobs ──────────────────────────────────────────────────────────────
# Captured live from categoryFeed.cfm?catID=148 (2026-07-01): <description> is
# "Company (City, State)", <title> is the job title.
_HIGHERED_XML = (
    b'<?xml version="1.0"?><rss version="2.0"><channel>'
    b'<title>HigherEdJobs - Faculty Affairs</title>'
    b'<item><title>Manager of Faculty Relations</title>'
    b'<description>Cleveland Institute of Music (Cleveland, OH)</description>'
    b'<link>https://www.higheredjobs.com/details.cfm?JobCode=179468928</link>'
    b'<guid>https://www.higheredjobs.com/details.cfm?JobCode=179468928</guid>'
    b'<pubDate>Wed, 10 Jun 2026 17:04:44 EDT</pubDate></item>'
    b'<item><title>Assistant Director of Academic Affairs</title>'
    b'<description>Columbia University (New York, NY)</description>'
    b'<link>https://www.higheredjobs.com/details.cfm?JobCode=179485814</link>'
    b'<pubDate>Tue, 30 Jun 2026 12:49:01 EDT</pubDate></item>'
    b'<item><title>Groundskeeper</title>'
    b'<description>Some College (Dayton, OH)</description>'
    b'<link>https://www.higheredjobs.com/details.cfm?JobCode=1</link>'
    b'<pubDate>Tue, 30 Jun 2026 12:49:01 EDT</pubDate></item>'
    b'</channel></rss>'
)


def test_higheredjobs_split_company_location():
    assert _split_company_location("Columbia University (New York, NY)") == (
        "Columbia University", "New York, NY")
    # No parenthetical -> whole string is company.
    assert _split_company_location("Just A Name") == ("Just A Name", "")
    assert _split_company_location("") == ("Unknown", "")


def test_higheredjobs_parse_title_company_location(tmp_path):
    from search.higheredjobs_client import _parse_feed
    c = _client(HigherEdJobsClient, tmp_path, industry="education")
    items = _parse_feed(_HIGHERED_XML)
    out = c.parse_results({"items": items}, "faculty")
    # "faculty" matches only the first item's title.
    assert [j.title for j in out] == ["Manager of Faculty Relations"]
    j = out[0]
    assert j.company == "Cleveland Institute of Music"
    assert j.location == "Cleveland, OH"
    assert j.source_api == "higheredjobs"
    assert j.job_id.startswith("higheredjobs_")


def test_higheredjobs_parse_matches_broad_keyword(tmp_path):
    from search.higheredjobs_client import _parse_feed
    c = _client(HigherEdJobsClient, tmp_path, industry="education")
    out = c.parse_results({"items": _parse_feed(_HIGHERED_XML)}, "director")
    assert "Assistant Director of Academic Affairs" in [j.title for j in out]


def test_higheredjobs_industry_gating():
    # Education-family fields activate; others get [] (self-skip).
    assert _categories_for_industry("education")           # truthy
    assert _categories_for_industry("higher education faculty")
    assert _categories_for_industry("teacher")
    assert _categories_for_industry("welding") == []
    assert _categories_for_industry("nursing") == []
    assert _categories_for_industry("") == []              # Alex default -> inert
    assert _categories_for_industry(None) == []


def test_higheredjobs_self_skip_search_returns_empty(tmp_path):
    # A welder's client fetches nothing (never hits the network — socket guard
    # would fire if it did).
    c = _client(HigherEdJobsClient, tmp_path, industry="welding")
    assert c.cat_ids == []
    assert c.search("welder", page=1) == {"items": []}


def test_higheredjobs_education_client_has_categories(tmp_path):
    c = _client(HigherEdJobsClient, tmp_path, industry="education")
    assert c.cat_ids  # non-empty -> would poll


# ── RNJobSite ─────────────────────────────────────────────────────────────────
# Captured live 2026-07-01: custom <hiringOrganization>/<jobLocation>, CDATA title.
_RN_XML = (
    b'<?xml version="1.0"?><rss version="2.0"><channel>'
    b'<title>Registered Nurse Jobs RSS</title>'
    b'<item><title><![CDATA[Director of Nursing (DON) - Hospice - Houston, TX]]></title>'
    b'<link>https://www.rnjobsite.com/registered-nurse/jobs/24186023</link>'
    b'<hiringOrganization><![CDATA[One Stop Recruiting]]></hiringOrganization>'
    b'<jobLocation><![CDATA[Houston TX]]></jobLocation>'
    b'<guid isPermaLink="true">https://www.rnjobsite.com/registered-nurse/jobs/24186023</guid>'
    b'<pubDate>Thu, 25 Jun 2026 15:18:17 EST</pubDate>'
    b'<description><![CDATA[Director of Nursing role, apply now.]]></description></item>'
    b'<item><title><![CDATA[Software Engineer]]></title>'
    b'<link>https://www.rnjobsite.com/registered-nurse/jobs/99</link>'
    b'<hiringOrganization><![CDATA[TechCo]]></hiringOrganization>'
    b'<jobLocation><![CDATA[Remote]]></jobLocation>'
    b'<pubDate>Thu, 25 Jun 2026 15:18:17 EST</pubDate>'
    b'<description><![CDATA[Build software.]]></description></item>'
    b'</channel></rss>'
)


def test_rnjobsite_parse_custom_tags(tmp_path):
    from search.rnjobsite_client import _parse_feed
    c = _client(RNJobSiteClient, tmp_path, industry="nursing")
    out = c.parse_results({"items": _parse_feed(_RN_XML)}, "nursing")
    assert [j.title for j in out] == ["Director of Nursing (DON) - Hospice - Houston, TX"]
    j = out[0]
    assert j.company == "One Stop Recruiting"
    assert j.location == "Houston TX"
    assert j.source_api == "rnjobsite"
    assert j.job_id.startswith("rnjobsite_")


def test_rnjobsite_industry_gating():
    assert _should_poll("nursing")
    assert _should_poll("registered nurse")
    assert _should_poll("healthcare")
    assert not _should_poll("welding")
    assert not _should_poll("controls engineering")
    assert not _should_poll("")        # Alex default -> inert
    assert not _should_poll(None)


def test_rnjobsite_self_skip_search_returns_empty(tmp_path):
    c = _client(RNJobSiteClient, tmp_path, industry="controls engineering")
    assert c.active is False
    assert c.search("engineer", page=1) == {"items": []}


def test_rnjobsite_dedup_across_base_and_specialty(tmp_path):
    # Same posting in base + specialty feed collapses on link.
    from search.rnjobsite_client import _parse_feed
    c = _client(RNJobSiteClient, tmp_path, industry="nursing")

    def fake_fetch(key, url):
        return _parse_feed(_RN_XML)

    c._fetch = fake_fetch  # type: ignore
    payload = c.search("nursing", page=1)
    links = [it["link"] for it in payload["items"]]
    assert len(links) == len(set(links))  # no dup links


# ── jobs.ac.uk (PROVISIONAL, opt-in) ──────────────────────────────────────────
_JOBSACUK_XML = (
    b'<?xml version="1.0"?><rss version="2.0"><channel>'
    b'<title>jobs.ac.uk</title>'
    b'<item><title>Lecturer in Adult Nursing</title>'
    b'<description>University of Somewhere. Full time.</description>'
    b'<link>https://www.jobs.ac.uk/job/ABC123</link>'
    b'<pubDate>Tue, 30 Jun 2026 12:49:01 GMT</pubDate></item>'
    b'</channel></rss>'
)


def test_jobsacuk_opt_in_default_off_us():
    # Default US project (no flag, no country) -> inert.
    assert opt_in_active("nursing", cfg={}) is False
    assert opt_in_active("nursing", cfg={"location": "Cincinnati, OH"}) is False


def test_jobsacuk_opt_in_via_flag():
    assert opt_in_active("nursing", cfg={"jobsacuk": True}) is True
    assert opt_in_active("nursing", cfg={"sources": {"jobsacuk": True}}) is True


def test_jobsacuk_opt_in_via_non_us_country():
    assert opt_in_active("nursing", cfg={"country": "gb"}) is True
    assert opt_in_active("nursing", cfg={"location": "London, United Kingdom"}) is True


def test_jobsacuk_inert_client_self_skips(tmp_path):
    c = _client(JobsAcUkClient, tmp_path, industry="nursing", opt_in=False)
    assert c.active is False
    assert c.search("nurse", page=1) == {"items": []}


def test_jobsacuk_parse_when_opted_in(tmp_path):
    from search.jobsacuk_client import _parse_feed
    c = _client(JobsAcUkClient, tmp_path, industry="nursing", opt_in=True)
    assert c.active is True
    out = c.parse_results({"items": _parse_feed(_JOBSACUK_XML)}, "nursing")
    assert [j.title for j in out] == ["Lecturer in Adult Nursing"]
    j = out[0]
    assert j.location == "United Kingdom"
    assert j.source_api == "jobsacuk"


# ── source_taxonomy shims ─────────────────────────────────────────────────────
def test_source_taxonomy_sector_gates():
    from search import source_taxonomy as st
    assert st.higheredjobs_active("education") is True
    assert st.higheredjobs_active("welding") is False
    assert st.rnjobsite_active("nursing") is True
    assert st.rnjobsite_active("welding") is False
    # sector_feed_applies delegates; unknown source -> True (no-op).
    assert st.sector_feed_applies("higheredjobs", "education") is True
    assert st.sector_feed_applies("higheredjobs", "welding") is False
    assert st.sector_feed_applies("rnjobsite", "nursing") is True
    assert st.sector_feed_applies("careers", "welding") is True


# ── registration ──────────────────────────────────────────────────────────────
def test_clients_registered_in_all_sources():
    from search.cli import ALL_SOURCES
    for s in ("higheredjobs", "rnjobsite", "jobsacuk"):
        assert s in ALL_SOURCES


def test_daily_sources_has_sector_feeds_but_not_jobsacuk():
    from config import DAILY_SOURCES
    assert "higheredjobs" in DAILY_SOURCES
    assert "rnjobsite" in DAILY_SOURCES
    assert "jobsacuk" not in DAILY_SOURCES  # opt-in only


def test_build_clients_sector_feeds_inert_for_eng(tmp_path, monkeypatch):
    # An engineering (empty-industry) build registers the sector clients but they
    # are inert — no network, no jobs.
    from search.cli import build_clients
    monkeypatch.setattr("config.CACHE_DIR", tmp_path)
    clients = build_clients(["higheredjobs", "rnjobsite", "jobsacuk"],
                            cache_enabled=False, industry_filter="")
    by_name = {type(c).__name__: c for c in clients}
    assert by_name["HigherEdJobsClient"].cat_ids == []
    assert by_name["RNJobSiteClient"].active is False
    assert by_name["JobsAcUkClient"].active is False
