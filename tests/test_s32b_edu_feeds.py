"""S32b K-12 education sources: REAP (per-state HTML portals) + EdJoin (public
JSON search). Parse from captured live fixtures + industry/state gating +
metro-first/state-fallback localization + self-skip. Fixtures are derived from
REAL captured responses (ohreap.net srch=100 and edjoin.org /Home/LoadJobs
?keywords=teacher, both fetched 2026-07-02)."""
import pytest

import industry_profile
from search.reap_client import (
    ReapClient,
    STATE_PORTALS,
    _is_education as reap_is_education,
    _parse_rows,
    _robots_allows,
    _split_school_location,
    _state_of,
    portal_for_location,
)
from search.edjoin_client import (
    EdjoinClient,
    _is_education as edjoin_is_education,
    _iso_from_ms_date,
    _location_of,
    _num,
    _salary,
    _target_state_is_ca,
)


@pytest.fixture(autouse=True)
def _clear_profile_cache():
    industry_profile.clear_cache()
    yield
    industry_profile.clear_cache()


def _client(cls, tmp_path, **kw):
    return cls(cache_dir=tmp_path, cache_enabled=False, **kw)


# ── REAP ──────────────────────────────────────────────────────────────────────
# Captured live from ohreap.net/jobsrch.php?srch=100 (2026-07-02): each posting is
# a <tr class="jobfirstrow"> with a /job_postings/{id}/{site}/{site} link, a title
# (+<div> subtitle + Certificate line), a school cell "District<br/>City, ST ZIP".
_REAP_HTML = (
    '<table><tbody>'
    '<tr class="jobfirstrow">'
    '<td class="td_num" valign="top">\xa01\xa0</td>'
    '<td align="left" class="" valign="top"><a href="/job_postings/4101/OH01/OH01">'
    '\n\t\tClassroom Teacher / Mathematics\t\t<div>Math at Newark High School</div>\n</a>'
    '<span style="color:#555;">Certificate:</span> HS (7-12) Mathematics\t\t</td>'
    '<td align="left" class="school" valign="top">Newark City SD<br/>Newark,\xa0OH\xa043055</td>'
    '<td align="left" class="dateTD" nowrap="nowrap" valign="top"><b>Jul 02</b> 26</td>'
    '<td class="" id="JOB4101" valign="top"><button>Add</button></td>'
    '</tr>'
    '<tr class="jobsecondRow"><td></td><td>Expand</td></tr>'
    '<tr class="jobfirstrow">'
    '<td class="td_num shaded" valign="top">\xa02\xa0</td>'
    '<td align="left" class="shaded" valign="top"><a href="/job_postings/4100/OH01/OH01">'
    '\n\t\tPrincipal\t\t<div>Elementary Principal at Wilson</div>\n</a>'
    '<span style="color:#555;">Certificate:</span> Administrative\t\t</td>'
    '<td align="left" class="school shaded" valign="top">Columbus City Schools<br/>Columbus,\xa0OH\xa043215</td>'
    '<td align="left" class="dateTD shaded" nowrap="nowrap" valign="top"><b>Jun 30</b> 26</td>'
    '<td class="shaded" id="JOB4100" valign="top"><button>Add</button></td>'
    '</tr>'
    '</tbody></table>'
)


def test_reap_parse_rows():
    rows = _parse_rows(_REAP_HTML, "ohreap.net")
    assert len(rows) == 2
    assert rows[0]["path"] == "/job_postings/4101/OH01/OH01"
    assert "Classroom Teacher / Mathematics" in rows[0]["title"]
    assert "Jul 02" in rows[0]["date"]
    # School cell keeps the <br> boundary as a newline for a clean split.
    assert "Newark City SD" in rows[0]["school_text"]
    assert "Newark, OH" in rows[0]["school_text"].replace("\n", " ")


def test_reap_split_school_location():
    assert _split_school_location("Newark City SD\nNewark, OH 43055") == (
        "Newark City SD", "Newark, OH")
    assert _split_school_location("Columbus City Schools\nColumbus, OH 43215") == (
        "Columbus City Schools", "Columbus, OH")
    # Bare City,ST with no district.
    assert _split_school_location("Dayton, OH 45402") == ("Unknown", "Dayton, OH")
    # No City,ST -> whole thing is the district.
    assert _split_school_location("Just A District Name") == ("Just A District Name", "")
    assert _split_school_location("") == ("Unknown", "")


def test_reap_state_routing():
    assert _state_of("Columbus, OH") == "oh"
    assert _state_of("Cincinnati, Ohio") == "oh"
    assert _state_of("St. Louis, MO") == "mo"
    assert _state_of("Austin, TX") == "tx"
    assert _state_of("Remote") is None
    assert _state_of("") is None
    # Portal routing: covered states resolve, others -> None.
    assert portal_for_location("Columbus, OH") == "ohreap.net"
    assert portal_for_location("St. Louis, MO") == "moreap.net"
    assert portal_for_location("Austin, TX") is None       # uncovered
    assert portal_for_location("Remote") is None
    # Every covered state maps to a *reap.net portal.
    for st, host in STATE_PORTALS.items():
        assert host.endswith("reap.net")


def test_reap_industry_gating():
    assert reap_is_education("education")
    assert reap_is_education("teacher")
    assert reap_is_education("higher education faculty")
    assert not reap_is_education("welding")
    assert not reap_is_education("nursing")
    assert not reap_is_education("")            # Alex default -> inert
    assert not reap_is_education(None)


def test_reap_active_requires_education_and_covered_state(tmp_path):
    # education + covered state -> active
    c1 = _client(ReapClient, tmp_path, industry="teacher", location="Columbus, OH")
    assert c1.active is True and c1.portal == "ohreap.net"
    # education + UNcovered state -> inert
    c2 = _client(ReapClient, tmp_path, industry="teacher", location="Austin, TX")
    assert c2.active is False and c2.portal is None
    # non-education + covered state -> inert
    c3 = _client(ReapClient, tmp_path, industry="welding", location="Columbus, OH")
    assert c3.active is False and c3.portal is None
    # Alex default (empty industry) -> inert
    c4 = _client(ReapClient, tmp_path, industry="", location="Columbus, OH")
    assert c4.active is False


def test_reap_self_skip_search_returns_empty(tmp_path):
    # A welder's / uncovered-state client fetches nothing (no network).
    c = _client(ReapClient, tmp_path, industry="welding", location="Columbus, OH")
    assert c.search("welder", page=1) == {"rows": []}
    c2 = _client(ReapClient, tmp_path, industry="teacher", location="Austin, TX")
    assert c2.search("teacher", page=1) == {"rows": []}


def test_reap_parse_results_end_to_end(tmp_path):
    c = _client(ReapClient, tmp_path, industry="education", location="Columbus, OH")
    rows = _parse_rows(_REAP_HTML, "ohreap.net")
    # No location threaded -> all rows (whole state).
    out = c.parse_results({"rows": rows, "_portal": "ohreap.net", "_location": ""}, "teacher")
    # "teacher" matches the Classroom Teacher row (not the Principal row).
    titles = [j.title for j in out]
    assert any("Classroom Teacher" in t for t in titles)
    j = next(j for j in out if "Classroom Teacher" in j.title)
    assert j.company == "Newark City SD"
    assert j.location == "Newark, OH"
    assert j.source_api == "reap"
    assert j.url == "https://www.ohreap.net/job_postings/4101/OH01/OH01"
    assert j.job_id.startswith("reap_")


def test_reap_metro_first_state_fallback(tmp_path):
    """Columbus target: the Columbus-metro row is preferred; if the metro filter
    matched nothing we'd fall back to statewide (never 0 for a covered state)."""
    c = _client(ReapClient, tmp_path, industry="education", location="Columbus, OH")
    rows = _parse_rows(_REAP_HTML, "ohreap.net")
    # 'principal' keyword -> the Columbus principal row (true Columbus metro hit).
    out = c.parse_results({"rows": rows, "_portal": "ohreap.net",
                           "_location": "Columbus, OH"}, "principal")
    assert [j.location for j in out] == ["Columbus, OH"]
    # 'teacher' -> only the Newark row exists; Newark isn't Columbus-CBSA, so the
    # metro filter empties -> state-fallback keeps the in-state Newark row.
    out2 = c.parse_results({"rows": rows, "_portal": "ohreap.net",
                            "_location": "Columbus, OH"}, "teacher")
    assert out2 and all(j.location.endswith(", OH") for j in out2)


def test_reap_remote_only_tags_nationwide(tmp_path):
    c = _client(ReapClient, tmp_path, industry="education", location="Remote")
    rows = _parse_rows(_REAP_HTML, "ohreap.net")
    out = c.parse_results({"rows": rows, "_portal": "ohreap.net",
                           "_location": "Remote"}, "teacher")
    assert out and "remote" in out[0].location.lower()


def test_reap_lazy_portal_resolves_from_search_location(tmp_path):
    """S32d finding-1 regression: a caller that builds ReapClient WITHOUT a
    construction-time location (the GUI/MCP build_clients path used to omit it)
    must still resolve its portal from the location passed into search()."""
    # Build exactly like the GUI/MCP path did: education industry, NO location.
    c = _client(ReapClient, tmp_path, industry="teacher", location=None)
    # Inert at construction (no location -> no portal).
    assert c.active is False and c.portal is None
    # search() with a covered-state location lazily resolves the portal and the
    # client becomes active (self-fetch is stubbed so no network is touched).
    c._portal_allows = lambda portal: True
    c._fetch_category = lambda portal, srch: []
    out = c.search("teacher", location="Columbus, OH", page=1)
    assert c.portal == "ohreap.net"
    assert c.active is True
    assert out["_portal"] == "ohreap.net"
    # An uncovered-state search location stays inert (no portal, empty rows).
    c2 = _client(ReapClient, tmp_path, industry="teacher", location=None)
    assert c2.search("teacher", location="Austin, TX", page=1) == {"rows": []}
    assert c2.portal is None
    # A non-education field never lazily activates even with a covered location.
    c3 = _client(ReapClient, tmp_path, industry="welding", location=None)
    assert c3.search("welder", location="Columbus, OH", page=1) == {"rows": []}
    assert c3.portal is None


def test_reap_robots_allows_helper():
    # No robots.txt content (empty) -> allowed.
    assert _robots_allows("", "/jobsrch.php") is True
    # A disallow under * that matches -> blocked.
    assert _robots_allows("User-agent: *\nDisallow: /jobsrch.php", "/jobsrch.php") is False
    # A disallow under * that does NOT match the path -> allowed.
    assert _robots_allows("User-agent: *\nDisallow: /admin", "/jobsrch.php") is True
    # A disallow under a DIFFERENT UA -> irrelevant to us -> allowed.
    assert _robots_allows("User-agent: BadBot\nDisallow: /", "/jobsrch.php") is True


# ── EdJoin ────────────────────────────────────────────────────────────────────
# Captured live from edjoin.org/Home/LoadJobs?keywords=teacher (2026-07-02):
# JSON with data[] of posting rows (positionTitle/districtName/city/stateName/
# postingID/postingDate MS-date/PayRange*/beginningSalary/endingSalary).
def _edjoin_payload(location=""):
    return {
        "_location": location,
        "data": [
            {
                "postingID": 2243925,
                "positionTitle": "Air Force ROTC Teacher - Anticipated 2026/2027",
                "districtName": "Antelope Valley Union High School District",
                "city": "Lancaster", "stateName": "California",
                "postingDate": "/Date(1782950400000)/",
                "beginningSalary": None, "endingSalary": None,
                "PayRangeFrom": "", "PayRangeTo": "",
                "salaryInfo": "Determined by the MIP", "jobType": "Teacher - High School",
            },
            {
                "postingID": 2245377,
                "positionTitle": "Classroom Teacher, 7-8 (Science) - Roosevelt",
                "districtName": "Modesto City Schools",
                "city": "Modesto", "stateName": "California",
                "postingDate": "/Date(1783000000000)/",
                "beginningSalary": "73091", "endingSalary": "135492",
                "PayRangeFrom": "", "PayRangeTo": "",
                "salaryInfo": "Salary Schedule", "jobType": "Teacher - Middle School",
            },
        ],
    }


def test_edjoin_ms_date_parse():
    assert _iso_from_ms_date("/Date(1782950400000)/") == "2026-07-02T00:00:00+00:00"
    assert _iso_from_ms_date("") == ""
    assert _iso_from_ms_date(None) == ""
    assert _iso_from_ms_date("garbage") == ""


def test_edjoin_salary_helpers():
    assert _num("73091") == 73091
    assert _num("135,492.00") == 135492
    assert _num("") is None
    assert _num(None) is None
    assert _num("12") is None            # below sane floor -> None
    lo, hi = _salary({"beginningSalary": "73091", "endingSalary": "135492"})
    assert (lo, hi) == (73091, 135492)
    # Prefer explicit range fields; null -> (None, None).
    assert _salary({"beginningSalary": None, "endingSalary": None,
                    "PayRangeFrom": "", "PayRangeTo": ""}) == (None, None)


def test_edjoin_location_of():
    assert _location_of({"city": "Lancaster", "stateName": "California"}) == "Lancaster, CA"
    assert _location_of({"city": "Modesto", "stateName": "California"}) == "Modesto, CA"
    # Empty city but resolvable state -> the 2-letter abbrev alone.
    assert _location_of({"city": "", "stateName": "California"}) == "CA"
    # Unmappable state name is passed through as-is.
    assert _location_of({"city": "Austin", "stateName": "Texas"}) == "Austin, TX"


def test_edjoin_industry_gating():
    assert edjoin_is_education("education")
    assert edjoin_is_education("teacher")
    assert not edjoin_is_education("welding")
    assert not edjoin_is_education("nursing")
    assert not edjoin_is_education("")           # Alex default -> inert
    assert not edjoin_is_education(None)


def test_edjoin_self_skip_search_returns_empty(tmp_path):
    c = _client(EdjoinClient, tmp_path, industry="welding", location="Los Angeles, CA")
    assert c.active is False
    assert c.search("teacher", page=1) == {"data": [], "_location": ""}


def test_edjoin_parse_end_to_end_ca_metro(tmp_path):
    c = _client(EdjoinClient, tmp_path, industry="education", location="Los Angeles, CA")
    out = c.parse_results(_edjoin_payload("Los Angeles, CA"), "teacher")
    # LA target: no exact-metro city in the fixture -> statewide-CA fallback keeps
    # both CA rows (a CA teacher wants CA jobs).
    assert len(out) == 2
    j = out[0]
    assert j.source_api == "edjoin"
    assert j.url == "https://www.edjoin.org/Home/JobPosting/2243925"
    assert j.job_id == "edjoin_2243925"
    # Salary parsed on the Modesto row.
    modesto = next(x for x in out if x.company == "Modesto City Schools")
    assert (modesto.salary_min, modesto.salary_max) == (73091, 135492)
    assert modesto.location == "Modesto, CA"


def test_edjoin_exact_metro_localizes(tmp_path):
    # Modesto target: an exact Modesto-metro row exists -> localize to just it.
    c = _client(EdjoinClient, tmp_path, industry="education", location="Modesto, CA")
    out = c.parse_results(_edjoin_payload("Modesto, CA"), "teacher")
    assert [j.location for j in out] == ["Modesto, CA"]


def test_edjoin_non_ca_metro_graceful_zero(tmp_path):
    # A non-CA metro: no CA city matches, non-CA target -> strict filter -> 0 rows,
    # no noise (the required graceful behavior for a non-covered metro).
    c = _client(EdjoinClient, tmp_path, industry="education", location="Columbus, OH")
    out = c.parse_results(_edjoin_payload("Columbus, OH"), "teacher")
    assert out == []


def test_edjoin_target_state_is_ca():
    assert _target_state_is_ca("Los Angeles, CA")
    assert _target_state_is_ca("Sacramento, California")
    assert not _target_state_is_ca("Columbus, OH")
    assert not _target_state_is_ca("")
    assert not _target_state_is_ca("Remote")


def test_edjoin_per_keyword():
    assert EdjoinClient.parallel_keywords is True


def test_edjoin_uses_honest_ua_no_browser_spoof(tmp_path):
    """S32d finding-4: EdJoin must use the app's honest User-Agent (the endpoint
    works with it — verified live) and NOT spoof a browser UA or the site's XHR
    header."""
    c = _client(EdjoinClient, tmp_path, industry="education", location="Los Angeles, CA")
    ua = c.session.headers.get("User-Agent", "")
    assert ua == "JobSearchTool/1.0 (personal use)"
    assert "Mozilla" not in ua and "Chrome" not in ua
    # No XHR-impersonation header (we are not pretending to be the site's own AJAX).
    assert "X-Requested-With" not in c.session.headers


def test_edjoin_robots_fail_closed(tmp_path, monkeypatch):
    """S32d finding-4: EdJoin now enforces robots.txt at fetch time like REAP and
    fails CLOSED — a disallowing/unverifiable robots.txt yields 0 rows and no
    LoadJobs fetch. 404 (the live state) = allowed."""
    c = _client(EdjoinClient, tmp_path, industry="education", location="Los Angeles, CA")

    class _Resp:
        def __init__(self, status, text=""):
            self.status_code, self.text = status, text

    # A disallow of the LoadJobs path -> _endpoint_allows False.
    monkeypatch.setattr(c.session, "get",
                        lambda url, **kw: _Resp(200, "User-agent: *\nDisallow: /Home/LoadJobs"))
    assert c._endpoint_allows() is False
    # And search() then fetches nothing (0 rows) — verified by making the LoadJobs
    # GET blow up if it were ever reached.
    def _boom(url, **kw):
        if "robots" in url:
            return _Resp(200, "User-agent: *\nDisallow: /Home/LoadJobs")
        raise AssertionError("LoadJobs must not be fetched when robots disallows")
    monkeypatch.setattr(c.session, "get", _boom)
    assert c.search("teacher", location="Los Angeles, CA", page=1)["data"] == []

    # 404 robots (the live state) -> allowed.
    monkeypatch.setattr(c.session, "get", lambda url, **kw: _Resp(404))
    assert c._endpoint_allows() is True

    # A network error fails CLOSED.
    import requests
    def _raise(url, **kw):
        raise requests.RequestException("boom")
    monkeypatch.setattr(c.session, "get", _raise)
    assert c._endpoint_allows() is False


# ── source_taxonomy shims ─────────────────────────────────────────────────────
def test_source_taxonomy_edu_gates():
    from search import source_taxonomy as st
    assert st.reap_active("education", "Columbus, OH") is True
    assert st.reap_active("education", "Austin, TX") is False       # uncovered state
    assert st.reap_active("welding", "Columbus, OH") is False
    assert st.edjoin_active("education") is True
    assert st.edjoin_active("welding") is False
    # sector_feed_applies delegates; unknown source -> True (no-op).
    assert st.sector_feed_applies("reap", "education", "Columbus, OH") is True
    assert st.sector_feed_applies("reap", "education", "Austin, TX") is False
    assert st.sector_feed_applies("edjoin", "education") is True
    assert st.sector_feed_applies("edjoin", "welding") is False
    assert st.sector_feed_applies("careers", "welding") is True


# ── registration ──────────────────────────────────────────────────────────────
def test_edu_feeds_registered_in_all_sources():
    from search.cli import ALL_SOURCES
    assert "reap" in ALL_SOURCES
    assert "edjoin" in ALL_SOURCES


def test_edu_feeds_in_daily_sources():
    from config import DAILY_SOURCES
    assert "reap" in DAILY_SOURCES
    assert "edjoin" in DAILY_SOURCES


def test_build_clients_edu_feeds_inert_for_eng(tmp_path, monkeypatch):
    # An engineering (empty-industry) build registers the edu clients but they are
    # inert — no network, no jobs.
    from search.cli import build_clients
    monkeypatch.setattr("config.CACHE_DIR", tmp_path)
    clients = build_clients(["reap", "edjoin"], cache_enabled=False,
                            industry_filter="", location="")
    by_name = {type(c).__name__: c for c in clients}
    assert by_name["ReapClient"].active is False
    assert by_name["EdjoinClient"].active is False


def test_build_clients_edu_feeds_active_for_education(tmp_path, monkeypatch):
    from search.cli import build_clients
    monkeypatch.setattr("config.CACHE_DIR", tmp_path)
    clients = build_clients(["reap", "edjoin"], cache_enabled=False,
                            industry_filter="education", location="Columbus, OH")
    by_name = {type(c).__name__: c for c in clients}
    # REAP active for OH (covered); EdJoin active for any education field.
    assert by_name["ReapClient"].active is True
    assert by_name["ReapClient"].portal == "ohreap.net"
    assert by_name["EdjoinClient"].active is True


def test_reap_ca_bundle_completes_chain_not_disables_verify():
    """The REAP TLS fix must ADD a trusted intermediate, NEVER disable verify."""
    from search.reap_client import _reap_ca_bundle, ReapClient
    bundle = _reap_ca_bundle()
    # A real file path (a CA bundle), not False / None.
    assert isinstance(bundle, str) and bundle
    import os
    assert os.path.exists(bundle)
    # The client wires verify to the bundle path (never False).
    c = ReapClient(cache_enabled=False, industry="education", location="Columbus, OH")
    assert c.session.verify == bundle
    assert c.session.verify is not False
