"""Feed-client parse/parsing-helper coverage.

These tests pin the CURRENT parse output of every keyless feed client
(remoteok / remotive / jobicy / himalayas / themuse / hn) on small fixed
sample payloads, so the SingleFeedClient extraction (FEEDS-3) cannot silently
change behavior. They also cover the parsing helpers directly: hn header/
first-line parse, himalayas ISO date + annualization, and salary salvage.

FEEDS-1 (boolean keyword matching for themuse/remoteok) and FEEDS-6
(himalayas salary-prepend + guid hash fallback) extend the relevant sections.
"""
import hashlib

import pytest

from match.scorer import salary_from_text
from search.himalayas_client import (
    HimalayasClient,
    _annualize,
    _iso_from_unix,
    _job_id,
)
from search.hn_client import HNClient, _comment_to_text, _parse_header
from search.jobicy_client import JobicyClient
from search.remoteok_client import RemoteOKClient
from search.remotive_client import RemotiveClient
from search.themuse_client import TheMuseClient


# ── helper: instantiate a client without hitting CACHE_DIR ────────────────────

def _client(cls, tmp_path):
    return cls(cache_dir=tmp_path, cache_enabled=False)


# ── himalayas helpers: annualization ──────────────────────────────────────────

@pytest.mark.parametrize("value,period,expected", [
    ("100000", "annual", 100000),
    ("100000", "yearly", 100000),
    ("100000", "annually", 100000),
    ("5000", "monthly", 60000),     # 5000 * 12
    ("50", "hourly", 104000),       # 50 * 2080
    ("10", "hourly", None),         # 20800 < 30k floor -> rejected
    ("600000", "annual", None),     # over 500k ceiling -> rejected
    ("20000", "annual", None),      # under 30k floor -> rejected
    (None, "annual", None),
    ("notanumber", "annual", None),
    ("100000", "", 100000),         # empty period defaults to yearly
])
def test_himalayas_annualize(value, period, expected):
    assert _annualize(value, period) == expected


# ── himalayas helpers: ISO date from UNIX timestamp ───────────────────────────

def test_himalayas_iso_from_unix():
    assert _iso_from_unix(1700000000) == "2023-11-14T22:13:20+00:00"


@pytest.mark.parametrize("bad", [None, "", "notanumber"])
def test_himalayas_iso_from_unix_bad(bad):
    assert _iso_from_unix(bad) == ""


# ── hn helpers: header parse + comment-to-text ────────────────────────────────

@pytest.mark.parametrize("line,expected", [
    ("Acme Corp | Controls Engineer | Cincinnati, OH | onsite",
     ("Acme Corp", "Controls Engineer", "Cincinnati, OH")),
    ("Acme Corp | Controls Engineer", ("Acme Corp", "Controls Engineer", "")),
    ("Acme Corp", ("Acme Corp", "", "")),
    ("", ("", "", "")),
])
def test_hn_parse_header(line, expected):
    assert _parse_header(line) == expected


def test_hn_comment_to_text_breaks_and_unescapes():
    html = "<p>Acme Corp | Controls Engineer | Remote<p>We build robots &amp; stuff"
    assert _comment_to_text(html) == "Acme Corp | Controls Engineer | Remote\nWe build robots & stuff"


# ── salary salvage (the scorer path the feeds feed into) ──────────────────────

def test_salary_from_text_recovers_dollar_range():
    assert salary_from_text("Salary: $130,000 - $160,000\nGreat role") == (130000.0, 160000.0)


# ── remoteok.parse_results ────────────────────────────────────────────────────

def _remoteok_payload():
    return {"jobs": [
        {
            "id": 42,
            "position": "Controls Engineer",
            "company": "Acme",
            "location": "",
            "tags": ["automation", "plc"],
            "description": "<p>We need a <b>controls</b> wizard.</p>",
            "salary_min": "90000",
            "salary_max": "120000",
            "url": "https://remoteok.com/jobs/42",
            "date": "2026-06-01",
        },
        {
            "id": 43,
            "position": "Marketing Lead",
            "company": "BrandCo",
            "location": "Remote",
            "tags": ["seo"],
            "description": "Run campaigns.",
            "url": "https://remoteok.com/jobs/43",
            "date": "2026-06-02",
        },
    ]}


def test_remoteok_parse_matches_on_title_and_tags(tmp_path):
    c = _client(RemoteOKClient, tmp_path)
    out = c.parse_results(_remoteok_payload(), "controls engineer")
    assert [j.title for j in out] == ["Controls Engineer"]
    j = out[0]
    assert j.company == "Acme"
    assert j.location == "Remote"          # blank -> Remote
    assert j.salary_min == 90000.0 and j.salary_max == 120000.0
    assert "<" not in j.description        # HTML stripped
    assert j.job_id == "42"
    assert j.source_api == "remoteok"


def test_remoteok_parse_routes_through_boolean_query(tmp_path):
    # FEEDS-1: remoteok now matches via scrape.text_match.keyword_matches on
    # title+tags (the bare token "engineer" now matches, where the old bespoke
    # stopword matcher stripped it to nothing and returned []).
    c = _client(RemoteOKClient, tmp_path)
    out = c.parse_results(_remoteok_payload(), "engineer")
    assert [j.title for j in out] == ["Controls Engineer"]


def test_remoteok_not_term_excludes(tmp_path):
    # FEEDS-1: a NOT term now excludes. "Senior Controls Engineer" must be
    # dropped by `controls NOT senior`; the old matcher ignored NOT entirely.
    payload = {"jobs": [{
        "id": 1, "position": "Senior Controls Engineer", "company": "Acme",
        "location": "", "tags": ["senior"], "description": "x",
        "url": "u", "date": "d",
    }]}
    c = _client(RemoteOKClient, tmp_path)
    assert c.parse_results(payload, "controls NOT senior") == []
    # Sanity: without the NOT it would match.
    assert len(c.parse_results(payload, "controls")) == 1


def test_themuse_not_term_excludes(tmp_path):
    # FEEDS-1: themuse routes through the boolean engine on title+contents, so
    # '"controls engineer" NOT senior' no longer matches "Senior Controls
    # Engineer" (the old stopword matcher ignored the NOT).
    payload = {"results": [{
        "id": 1, "name": "Senior Controls Engineer",
        "company": {"name": "Acme"}, "locations": [{"name": "Remote"}],
        "contents": "Senior controls engineer role.",
        "refs": {"landing_page": "u"}, "publication_date": "d",
    }]}
    c = _client(TheMuseClient, tmp_path)
    assert c.parse_results(payload, '"controls engineer" NOT senior') == []
    # Sanity: without the NOT it matches.
    assert len(c.parse_results(payload, '"controls engineer"')) == 1


# ── remotive.parse_results ────────────────────────────────────────────────────

def _remotive_payload():
    return {"jobs": [
        {
            "id": 7,
            "title": "Controls Engineer",
            "company_name": "Acme",
            "category": "Engineering",
            "tags": ["plc"],
            "candidate_required_location": "USA",
            "description": "<p>Build control systems.</p>",
            "salary": "$130,000 - $160,000",
            "url": "https://remotive.com/jobs/7",
            "publication_date": "2026-06-01",
        },
        {
            "id": 8,
            "title": "Sales Rep",
            "company_name": "BrandCo",
            "category": "Sales",
            "tags": [],
            "description": "Sell things.",
            "url": "https://remotive.com/jobs/8",
            "publication_date": "2026-06-02",
        },
    ]}


def test_remotive_parse_and_salary_prepend(tmp_path):
    c = _client(RemotiveClient, tmp_path)
    out = c.parse_results(_remotive_payload(), "controls engineer")
    assert [j.title for j in out] == ["Controls Engineer"]
    j = out[0]
    assert j.company == "Acme"
    assert j.location == "USA"
    assert j.job_id == "remotive_7"
    assert j.source_api == "remotive"
    # Freeform salary prepended so the scorer can recover it.
    assert j.description.startswith("Salary: $130,000 - $160,000")
    assert salary_from_text(j.description) == (130000.0, 160000.0)


# ── jobicy.parse_results ──────────────────────────────────────────────────────

def _jobicy_payload():
    return {"jobs": [
        {
            "id": 11,
            "jobTitle": "Controls Engineer",
            "companyName": "Acme",
            "jobIndustry": ["Engineering"],
            "jobGeo": "Anywhere",
            "jobDescription": "<p>Controls work.</p>",
            "url": "https://jobicy.com/jobs/11",
            "pubDate": "2026-06-01",
        },
        {
            "id": 12,
            "jobTitle": "Recruiter",
            "companyName": "BrandCo",
            "jobIndustry": ["HR"],
            "jobGeo": "Remote",
            "jobDescription": "Hire people.",
            "url": "https://jobicy.com/jobs/12",
            "pubDate": "2026-06-02",
        },
    ]}


def test_jobicy_parse(tmp_path):
    c = _client(JobicyClient, tmp_path)
    out = c.parse_results(_jobicy_payload(), "controls engineer")
    assert [j.title for j in out] == ["Controls Engineer"]
    j = out[0]
    assert j.company == "Acme"
    assert j.location == "Anywhere"
    assert j.job_id == "jobicy_11"
    assert j.source_api == "jobicy"
    assert "<" not in j.description


# ── himalayas.parse_results ───────────────────────────────────────────────────

def _himalayas_payload():
    return {"jobs": [
        {
            "guid": "abc123",
            "title": "Controls Engineer",
            "companyName": "Acme",
            "categories": ["Engineering"],
            "locationRestrictions": ["USA", "Canada"],
            "description": "<p>Build controls.</p>",
            "minSalary": "100000",
            "maxSalary": "140000",
            "salaryPeriod": "annual",
            "applicationLink": "https://himalayas.app/jobs/abc123",
            "pubDate": 1700000000,
        },
        {
            "guid": "def456",
            "title": "Designer",
            "companyName": "BrandCo",
            "categories": ["Design"],
            "description": "Make things pretty.",
            "applicationLink": "https://himalayas.app/jobs/def456",
            "pubDate": 1700000000,
        },
    ]}


def test_himalayas_parse(tmp_path):
    c = _client(HimalayasClient, tmp_path)
    out = c.parse_results(_himalayas_payload(), "controls engineer")
    assert [j.title for j in out] == ["Controls Engineer"]
    j = out[0]
    assert j.company == "Acme"
    assert j.location == "USA, Canada"
    assert j.salary_min == 100000 and j.salary_max == 140000
    assert j.created == "2023-11-14T22:13:20+00:00"
    assert j.job_id == "himalayas_abc123"
    assert j.source_api == "himalayas"
    assert "<" not in j.description


# ── FEEDS-6: himalayas salary salvage + guid hash fallback ─────────────────────

def test_himalayas_salary_text_prepended_and_salvaged(tmp_path):
    # min/maxSalary null but a freeform salaryDescription is present -> prepend
    # it so the scorer can recover the range (mirrors remotive_client).
    payload = {"jobs": [{
        "guid": "g1", "title": "Controls Engineer", "companyName": "Acme",
        "categories": ["Engineering"], "description": "<p>Build controls.</p>",
        "salaryDescription": "$130,000 - $160,000", "salaryPeriod": "",
        "applicationLink": "https://himalayas.app/jobs/g1", "pubDate": 1700000000,
    }]}
    c = _client(HimalayasClient, tmp_path)
    j = c.parse_results(payload, "controls engineer")[0]
    assert j.salary_min is None and j.salary_max is None   # no structured fields
    assert j.description.startswith("Salary: $130,000 - $160,000")
    assert salary_from_text(j.description) == (130000.0, 160000.0)


def test_himalayas_salary_prepend_before_truncation(tmp_path):
    # The prepend must happen BEFORE the 3000-char cut so a long description
    # cannot push the salary line out of the salvageable window.
    payload = {"jobs": [{
        "guid": "g2", "title": "Controls Engineer", "companyName": "Acme",
        "categories": ["Engineering"], "description": "controls " * 1000,
        "salaryDescription": "$130,000 - $160,000",
        "applicationLink": "u", "pubDate": 1700000000,
    }]}
    c = _client(HimalayasClient, tmp_path)
    j = c.parse_results(payload, "controls engineer")[0]
    assert len(j.description) == 3000
    assert j.description.startswith("Salary: $130,000 - $160,000")


def test_himalayas_job_id_hash_fallback_when_guid_empty():
    # Empty guid no longer collapses to the bare prefix; distinct postings get
    # distinct ids (md5 of url, or title|company when url is missing too).
    a = _job_id("", "https://himalayas.app/jobs/a", "Controls Engineer", "Acme")
    b = _job_id("", "https://himalayas.app/jobs/b", "Controls Engineer", "Acme")
    assert a != b
    assert a != "himalayas_" and b != "himalayas_"
    assert a.startswith("himalayas_")
    # No url -> fall back to title|company.
    c1 = _job_id("", "", "Controls Engineer", "Acme")
    c2 = _job_id("", "", "Data Scientist", "Acme")
    assert c1 != c2 and c1 != "himalayas_"
    # Present guid still wins.
    assert _job_id("abc", "u", "t", "co") == "himalayas_abc"


def test_himalayas_two_empty_guid_jobs_stay_distinct(tmp_path):
    payload = {"jobs": [
        {"guid": "", "title": "Controls Engineer", "companyName": "Acme",
         "categories": ["Engineering"], "description": "x",
         "applicationLink": "https://himalayas.app/jobs/a", "pubDate": 1700000000},
        {"guid": "", "title": "Controls Engineer", "companyName": "Beta",
         "categories": ["Engineering"], "description": "x",
         "applicationLink": "https://himalayas.app/jobs/b", "pubDate": 1700000000},
    ]}
    c = _client(HimalayasClient, tmp_path)
    out = c.parse_results(payload, "controls engineer")
    ids = {j.job_id for j in out}
    assert len(ids) == 2                       # not collapsed to one bucket
    assert "himalayas_" not in ids


# ── themuse.parse_results ─────────────────────────────────────────────────────

def _themuse_payload():
    return {"results": [
        {
            "id": 99,
            "name": "Controls Engineer",
            "company": {"name": "Acme"},
            "locations": [{"name": "Cincinnati, OH"}],
            "contents": "<p>We build <b>controls</b> systems &amp; more.</p>",
            "refs": {"landing_page": "https://themuse.com/jobs/99"},
            "publication_date": "2026-06-01",
        },
        {
            "id": 100,
            "name": "Accountant",
            "company": {"name": "BrandCo"},
            "locations": [{"name": "Remote"}],
            "contents": "Crunch numbers.",
            "refs": {"landing_page": "https://themuse.com/jobs/100"},
            "publication_date": "2026-06-02",
        },
    ]}


def test_themuse_parse(tmp_path):
    c = _client(TheMuseClient, tmp_path)
    out = c.parse_results(_themuse_payload(), "controls engineer")
    assert [j.title for j in out] == ["Controls Engineer"]
    j = out[0]
    assert j.company == "Acme"
    assert j.location == "Cincinnati, OH"
    assert j.salary_min is None and j.salary_max is None
    assert j.job_id == "99"
    assert j.source_api == "themuse"
    assert "<" not in j.description
    assert "&amp;" not in j.description    # entity decoded


# ── hn.parse_results ──────────────────────────────────────────────────────────

def _hn_payload():
    return {"hits": [
        {
            "objectID": "555",
            "comment_text": "<p>Acme Corp | Controls Engineer | Cincinnati, OH<p>"
                            "We build robots. Email jobs@acme.example",
            "created_at": "2026-06-01T00:00:00Z",
        },
        {
            "objectID": "556",
            "comment_text": "<p>Just replying to the thread, no pipes here.",
            "created_at": "2026-06-02T00:00:00Z",
        },
    ]}


def test_hn_parse(tmp_path):
    c = _client(HNClient, tmp_path)
    out = c.parse_results(_hn_payload(), "controls")
    # Only the pipe-formatted top-level post becomes a job.
    assert [j.company for j in out] == ["Acme Corp"]
    j = out[0]
    assert j.title == "Controls Engineer"
    assert j.location == "Cincinnati, OH"
    assert j.url == "https://news.ycombinator.com/item?id=555"
    assert j.job_id == "hn_555"
    assert j.source_api == "hn"
