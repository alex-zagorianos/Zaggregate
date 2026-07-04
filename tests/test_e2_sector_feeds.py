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
    _parse_feed,
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


# ── S32d finding-2: state-aware metro localization (false-drop / false-keep) ──
# A metro-bound national-feed search must (1) KEEP legitimate in-metro suburb rows
# in a CBSA member state (fail open to same-state), and (2) REJECT a same-name
# out-of-state city that only matched the bare-city substring ("Columbus, GA" for
# a "Columbus, OH" seeker).
def _rn_feed(*rows):
    items = b"".join(
        b'<item><title><![CDATA[Registered Nurse - ' + t.encode() + b']]></title>'
        b'<link>https://www.rnjobsite.com/registered-nurse/jobs/' + str(i).encode() + b'</link>'
        b'<hiringOrganization><![CDATA[Health System]]></hiringOrganization>'
        b'<jobLocation><![CDATA[' + loc.encode() + b']]></jobLocation>'
        b'<pubDate>Thu, 25 Jun 2026 15:18:17 EST</pubDate>'
        b'<description><![CDATA[A nursing role.]]></description></item>'
        for i, (t, loc) in enumerate(rows)
    )
    return (b'<?xml version="1.0"?><rss version="2.0"><channel><title>RN</title>'
            + items + b'</channel></rss>')


def test_rnjobsite_metro_keeps_in_state_suburb_drops_out_of_state_samename(tmp_path):
    from search.rnjobsite_client import _parse_feed
    c = _client(RNJobSiteClient, tmp_path, industry="nursing")
    xml = _rn_feed(
        ("A", "Edgewood, KY"),       # genuine Cincinnati-metro suburb (KY member state)
        ("B", "Hamilton, OH"),       # genuine Cincinnati-metro suburb (OH)
        ("C", "Columbus, GA"),       # same-name OUT-of-state city -> must be dropped
        ("D", "Cincinnati, OH"),     # true metro
    )
    out = c.parse_results({"items": _parse_feed(xml), "_location": "Cincinnati, OH"},
                          "nurse")
    locs = {j.location for j in out}
    assert "Cincinnati, OH" in locs               # metro row kept
    assert "Edgewood, KY" in locs                 # in-state suburb kept (was false-dropped)
    assert "Hamilton, OH" in locs                 # in-state suburb kept
    assert "Columbus, GA" not in locs             # out-of-state same-name rejected


def test_rnjobsite_metro_false_keep_rejected_for_columbus(tmp_path):
    from search.rnjobsite_client import _parse_feed
    c = _client(RNJobSiteClient, tmp_path, industry="nursing")
    xml = _rn_feed(("A", "Columbus, GA"), ("B", "Columbus, OH"))
    out = c.parse_results({"items": _parse_feed(xml), "_location": "Columbus, OH"},
                          "nurse")
    assert [j.location for j in out] == ["Columbus, OH"]   # GA row gone


def test_rnjobsite_metro_fail_open_when_no_exact_metro(tmp_path):
    # Only in-state (non-metro) rows exist -> fail open to same-state, not 0.
    from search.rnjobsite_client import _parse_feed
    c = _client(RNJobSiteClient, tmp_path, industry="nursing")
    xml = _rn_feed(("A", "Toledo, OH"), ("B", "Columbus, GA"))
    out = c.parse_results({"items": _parse_feed(xml), "_location": "Cincinnati, OH"},
                          "nurse")
    # Toledo (OH, in-state, not Cincinnati-metro) survives; the GA row does not.
    assert [j.location for j in out] == ["Toledo, OH"]


def _highered_feed(*rows):
    items = b"".join(
        b'<item><title>Professor of Nursing</title>'
        b'<description>' + f"{comp} ({loc})".encode() + b'</description>'
        b'<link>https://www.higheredjobs.com/details.cfm?JobCode=' + str(i).encode() + b'</link>'
        b'<pubDate>Wed, 10 Jun 2026 17:04:44 EDT</pubDate></item>'
        for i, (comp, loc) in enumerate(rows)
    )
    return (b'<?xml version="1.0"?><rss version="2.0"><channel><title>H</title>'
            + items + b'</channel></rss>')


def test_higheredjobs_metro_state_aware_keep_suburb_drop_out_of_state(tmp_path):
    from search.higheredjobs_client import _parse_feed
    c = _client(HigherEdJobsClient, tmp_path, industry="education")
    xml = _highered_feed(
        ("Edgewood College", "Edgewood, KY"),
        ("Hamilton U", "Hamilton, OH"),
        ("Columbus State GA", "Columbus, GA"),
        ("UC", "Cincinnati, OH"),
    )
    out = c.parse_results({"items": _parse_feed(xml), "_location": "Cincinnati, OH"},
                          "professor")
    locs = {j.location for j in out}
    assert {"Cincinnati, OH", "Edgewood, KY", "Hamilton, OH"} <= locs
    assert "Columbus, GA" not in locs


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


def test_daily_sources_has_sector_feeds_and_jobsacuk():
    # S35: jobsacuk now registers in the daily net too — it self-gates via its
    # OWN opt_in_active() (truthy config flag OR non-US adzuna_country_for), the
    # same "register but inert by default" contract higheredjobs/rnjobsite
    # already use. A default US project never satisfies either trigger, so it
    # stays a zero-network no-op (test_build_clients_sector_feeds_inert_for_eng
    # below pins that).
    from config import DAILY_SOURCES
    assert "higheredjobs" in DAILY_SOURCES
    assert "rnjobsite" in DAILY_SOURCES
    assert "jobsacuk" in DAILY_SOURCES


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
