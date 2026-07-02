"""S32: remote-only search intent + national-feed localization.

Covers the shared `search.remote_intent` helpers and the client wiring that fixes
remote-only coverage (Adzuna/USAJobs returned 0 for "Remote") and the national
sector-feed death-at-the-gate (RNJobSite/HigherEdJobs 244 -> 0 through the metro
gate). Non-remote behavior must stay byte-identical.
"""
import pytest

from search.remote_intent import (
    is_remote_only, metro_variant_set, remote_region_of, tag_nationwide_remote)


# ── is_remote_only ────────────────────────────────────────────────────────────
@pytest.mark.parametrize("loc", [
    "Remote", "remote", "REMOTE", "  Remote  ", "Remote (US)", "US Remote",
    "Remote - US", "Remote, USA", "Remote Nationwide", "Remote (Nationwide)",
    "anywhere", "Work From Home", "Remote-first", "Remote / US", "US-Remote",
    "Remote, United States", "Telework", "virtual",
])
def test_remote_only_true(loc):
    assert is_remote_only(loc) is True


@pytest.mark.parametrize("loc", [
    "", None, "Cincinnati, OH", "Boise, ID", "Austin", "New York, NY",
    "Remote Cincinnati",       # carries a real metro -> NOT remote-only
    "Seattle (Remote OK)",     # a metro that also allows remote is a located search
    "San Francisco Bay Area",
])
def test_remote_only_false(loc):
    assert is_remote_only(loc) is False


def test_remote_region():
    assert remote_region_of("Remote, US") == "us"
    assert remote_region_of("US Remote") == "us"
    assert remote_region_of("Remote Nationwide") == "us"
    assert remote_region_of("Remote") is None          # unqualified
    assert remote_region_of("anywhere") is None
    assert remote_region_of(None) is None


# ── tag_nationwide_remote ─────────────────────────────────────────────────────
def test_tag_preserves_origin_city():
    assert tag_nationwide_remote("Houston TX", "us") == "Houston TX (Remote, US)"
    assert tag_nationwide_remote("Houston TX", None) == "Houston TX (Remote)"


def test_tag_empty_location():
    assert tag_nationwide_remote("", "us") == "Remote, US"
    assert tag_nationwide_remote(None, None) == "Remote"


def test_tag_already_remote_untouched():
    assert tag_nationwide_remote("Remote, US", "us") == "Remote, US"
    assert tag_nationwide_remote("Austin (Remote)", "us") == "Austin (Remote)"


# ── metro_variant_set ─────────────────────────────────────────────────────────
def test_metro_variants_include_bare_city():
    mv = metro_variant_set("Boise, ID")
    assert "boise, id" in mv
    assert "boise" in mv


def test_metro_variants_empty_for_empty():
    assert metro_variant_set("") == set()
    assert metro_variant_set(None) == set()


# ── Adzuna query construction ─────────────────────────────────────────────────
def _adzuna(monkeypatch):
    from search.adzuna_client import AdzunaClient
    c = AdzunaClient(app_id="x", app_key="y", cache_enabled=False)
    captured = {}

    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"results": []}

    def _get(url, params=None, timeout=None):
        captured.clear()
        captured.update(params)
        return _Resp()

    c.session.get = _get
    return c, captured


def test_adzuna_remote_drops_where_and_marks_what(monkeypatch):
    c, cap = _adzuna(monkeypatch)
    c.search("marketing manager", location="Remote", page=1)
    assert cap["what"] == "remote marketing manager"
    assert "where" not in cap                 # nationwide (no geocoded place)


def test_adzuna_metro_unchanged(monkeypatch):
    c, cap = _adzuna(monkeypatch)
    c.search("marketing manager", location="Cincinnati, OH", page=1)
    assert cap["what"] == "marketing manager"
    assert cap["where"] == "Cincinnati, OH"


def test_adzuna_remote_tags_only_remote_rows(monkeypatch):
    c, _ = _adzuna(monkeypatch)
    raw = {
        "_remote_intent": True,
        "results": [
            {"title": "Mgr (Remote)", "company": {"display_name": "A"},
             "location": {"display_name": "Austin, TX"},
             "description": "fully remote", "redirect_url": "u1", "id": 1},
            {"title": "Onsite Mgr", "company": {"display_name": "B"},
             "location": {"display_name": "Dallas, TX"},
             "description": "in office", "redirect_url": "u2", "id": 2},
        ],
    }
    rows = c.parse_results(raw, "manager")
    locs = {r.title: r.location for r in rows}
    assert locs["Mgr (Remote)"] == "Austin, TX (Remote)"   # remote row tagged
    assert locs["Onsite Mgr"] == "Dallas, TX"              # non-remote untouched


def test_adzuna_non_remote_parse_unchanged(monkeypatch):
    c, _ = _adzuna(monkeypatch)
    raw = {
        "results": [
            {"title": "Mgr", "company": {"display_name": "A"},
             "location": {"display_name": "Austin, TX"},
             "description": "remote friendly", "redirect_url": "u1", "id": 1},
        ],
    }
    rows = c.parse_results(raw, "manager")
    assert rows[0].location == "Austin, TX"   # no _remote_intent -> no tag


# ── USAJobs query construction ────────────────────────────────────────────────
def _usajobs():
    from search.usajobs_client import USAJobsClient
    c = USAJobsClient(api_key="k", user_agent="e@x.com", cache_enabled=False)
    captured = {}

    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"SearchResult": {"SearchResultItems": []}}

    def _get(url, headers=None, params=None, timeout=None):
        captured.clear()
        captured.update(params)
        return _Resp()

    c.session.get = _get
    return c, captured


def test_usajobs_remote_uses_indicator_no_location():
    c, cap = _usajobs()
    c.search("nurse", location="Remote", page=1)
    assert cap["RemoteIndicator"] == "True"
    assert "LocationName" not in cap


def test_usajobs_metro_uses_location_no_indicator():
    c, cap = _usajobs()
    c.search("nurse", location="Boise, ID", page=1)
    assert cap["LocationName"] == "Boise, ID"
    assert "RemoteIndicator" not in cap


# ── National sector-feed localization (RNJobSite) ─────────────────────────────
def _rn_items():
    return [
        {"title": "RN - ICU", "company": "Houston Health", "location": "Houston TX",
         "description": "bedside RN", "link": "l1", "pubDate": "p"},
        {"title": "RN - Med/Surg", "company": "Boise Clinic", "location": "Boise ID",
         "description": "bedside RN", "link": "l2", "pubDate": "p"},
        {"title": "RN Telehealth", "company": "TeleCo", "location": "Remote",
         "description": "remote RN", "link": "l3", "pubDate": "p"},
    ]


def _rn_client():
    from search.rnjobsite_client import RNJobSiteClient
    return RNJobSiteClient(cache_enabled=False, industry="nursing")


def test_rnjobsite_metro_localizes_drops_out_of_area():
    c = _rn_client()
    out = c.parse_results({"items": _rn_items(), "_location": "Boise, ID"}, "rn")
    titles = {j.title for j in out}
    assert "RN - Med/Surg" in titles          # Boise row survives (real locality)
    assert "RN Telehealth" in titles          # remote row survives
    assert "RN - ICU" not in titles           # Houston row dropped (national noise)


def test_rnjobsite_remote_tags_nationwide():
    c = _rn_client()
    out = c.parse_results({"items": _rn_items(), "_location": "Remote"}, "rn")
    # Every kept row reads as remote so the remote_ok gate keeps it.
    assert out, "remote search should keep national rows"
    for j in out:
        assert "remote" in j.location.lower()
    locs = {j.title: j.location for j in out}
    assert locs["RN - ICU"] == "Houston TX (Remote)"   # origin city preserved


def test_rnjobsite_no_location_unchanged():
    # Legacy / Alex path: no _location key -> no localization, no tagging.
    c = _rn_client()
    out = c.parse_results({"items": _rn_items()}, "rn")
    assert {j.title for j in out} == {"RN - ICU", "RN - Med/Surg", "RN Telehealth"}
    locs = {j.title: j.location for j in out}
    assert locs["RN - ICU"] == "Houston TX"            # untouched


def test_rnjobsite_search_threads_location():
    c = _rn_client()
    c._fetch = lambda key, url: []          # no network
    payload = c.search("rn", location="Boise, ID", page=1)
    assert payload["_location"] == "Boise, ID"


# ── HigherEdJobs shares the pattern ───────────────────────────────────────────
def _he_items():
    return [
        {"title": "Faculty - Nursing", "description": "Boise State (Boise, ID)",
         "link": "h1", "pubDate": "p"},
        {"title": "Faculty - Nursing", "description": "Columbia University (New York, NY)",
         "link": "h2", "pubDate": "p"},
    ]


def _he_client():
    from search.higheredjobs_client import HigherEdJobsClient
    return HigherEdJobsClient(cache_enabled=False, industry="education")


def test_higheredjobs_metro_localizes():
    c = _he_client()
    out = c.parse_results({"items": _he_items(), "_location": "Boise, ID"}, "faculty")
    locs = {j.company: j.location for j in out}
    assert "Boise State" in locs               # local row survives
    assert "Columbia University" not in locs    # NY row dropped for a Boise user


def test_higheredjobs_remote_tags_nationwide():
    c = _he_client()
    out = c.parse_results({"items": _he_items(), "_location": "Remote, US"}, "faculty")
    assert out
    for j in out:
        assert "remote" in j.location.lower()


def test_higheredjobs_no_location_unchanged():
    c = _he_client()
    out = c.parse_results({"items": _he_items()}, "faculty")
    locs = {j.company: j.location for j in out}
    assert locs["Boise State"] == "Boise, ID"
    assert locs["Columbia University"] == "New York, NY"


def test_higheredjobs_search_threads_location():
    c = _he_client()
    c._fetch_category = lambda cat_id: []    # no network
    payload = c.search("faculty", location="Columbus, OH", page=1)
    assert payload["_location"] == "Columbus, OH"
