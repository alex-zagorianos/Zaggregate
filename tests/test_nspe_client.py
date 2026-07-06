"""NSPE Career Center RSS client: parse from a captured-live fixture + industry
gating + self-skip. Fixture rows are scrubbed from a REAL fetch of
https://careers.nspe.org/jobs?display=rss&keywords=mechanical (2026-07-05,
HTTP 200, 31 items), plus two synthetic edge-case rows (no " | " delimiter in
title; an unparseable/no-prefix description) per the binding test requirement
-- mirrors tests/test_e2_sector_feeds.py's fixture-derivation pattern for the
sibling sector feeds (HigherEdJobs/RNJobSite)."""
import pytest

import industry_profile
from search.nspe_client import (
    NspeClient,
    _job_id_from_link,
    _leading_location,
    _parse_feed,
    _split_title_company,
    _terms_for_industry,
)


@pytest.fixture(autouse=True)
def _clear_profile_cache():
    industry_profile.clear_cache()
    yield
    industry_profile.clear_cache()


def _client(tmp_path, **kw):
    return NspeClient(cache_dir=tmp_path, cache_enabled=False, **kw)


# ── fixture: 5 items scrubbed from the real 2026-07-05 capture ───────────────
# Item 1/2: real rows (title has " | Company", description has "City, State, ").
# Item 3: real row with a real-world em-dash title still "| Company" delimited.
# Item 4: SYNTHETIC — title has NO " | " delimiter (guard row, company=Unknown).
# Item 5: SYNTHETIC — description has no parseable "City, State," prefix.
_NSPE_XML = (
    b'<?xml version="1.0"?><rss version="2.0"><channel>'
    b'<title>NSPE Career Center Jobs RSS</title>'
    b'<item>'
    b'<link>https://careers.nspe.org/jobs/rss/22273101/senior-mechanical-engineer</link>'
    b'<title>Senior Mechanical Engineer | Little</title>'
    b'<guid isPermaLink="true">https://careers.nspe.org/jobs/rss/22273101/senior-mechanical-engineer</guid>'
    b'<description>Charlotte, North Carolina,  Little is currently seeking a '
    b'Senior Mechanical Project Engineer to join our Charlotte, NC office.</description>'
    b'<pubDate>Wed, 13 May 2026 09:56:22 -0400</pubDate>'
    b'</item>'
    b'<item>'
    b'<link>https://careers.nspe.org/jobs/rss/22318850/mechanical-engineer-discipline-lead</link>'
    b'<title>Mechanical Engineer - Discipline Lead | Little</title>'
    b'<description>Charlotte, North Carolina,  Little is currently seeking a '
    b'Mechanical Engineer Discipline Lead.</description>'
    b'<pubDate>Tue, 02 Jun 2026 14:35:03 -0400</pubDate>'
    b'</item>'
    b'<item>'
    b'<link>https://careers.nspe.org/jobs/rss/22318845/principal-turbomachinery-engineer</link>'
    b'<title>Principal Turbomachinery Engineer | Barber-Nichols LLC</title>'
    b'<description>Arvada, Colorado,  Barber-Nichols is seeking a Principal '
    b'Turbomachinery Engineer for our design team.</description>'
    b'<pubDate>Fri, 05 Jun 2026 09:28:18 -0400</pubDate>'
    b'</item>'
    b'<item>'
    b'<link>https://careers.nspe.org/jobs/rss/99999001/some-posting</link>'
    b'<title>Manufacturing Engineer Opening</title>'
    b'<description>Toledo, Ohio,  A great manufacturing engineer role.</description>'
    b'<pubDate>Mon, 08 Jun 2026 15:30:14 -0400</pubDate>'
    b'</item>'
    b'<item>'
    b'<link>https://careers.nspe.org/jobs/rss/99999002/industrial-eng</link>'
    b'<title>Industrial Engineer | Acme Corp</title>'
    b'<description>Apply now! This role has flexible remote options and great '
    b'benefits for the right industrial engineer.</description>'
    b'<pubDate>Wed, 01 Jul 2026 14:26:57 -0400</pubDate>'
    b'</item>'
    b'</channel></rss>'
)


# ── unit helpers ──────────────────────────────────────────────────────────────
def test_nspe_split_title_company():
    assert _split_title_company("Senior Mechanical Engineer | Little") == (
        "Senior Mechanical Engineer", "Little")
    # No " | " delimiter -> whole title kept, company falls back to Unknown.
    assert _split_title_company("Manufacturing Engineer Opening") == (
        "Manufacturing Engineer Opening", "Unknown")
    assert _split_title_company("") == ("", "Unknown")
    # A company name containing " | " itself: rsplit on the LAST occurrence
    # keeps the earlier " | " as part of the title.
    assert _split_title_company("Role A | B | RealCo") == ("Role A | B", "RealCo")


def test_nspe_leading_location_parses_city_state():
    assert _leading_location(
        "Charlotte, North Carolina,  Little is currently seeking a Senior "
        "Mechanical Project Engineer."
    ) == "Charlotte, North Carolina"


def test_nspe_leading_location_empty_when_unparseable():
    # No leading "City, State," prefix -> "" (never drop the row for it).
    assert _leading_location(
        "Apply now! This role has flexible remote options."
    ) == ""
    assert _leading_location("") == ""
    assert _leading_location(None) == ""


def test_nspe_job_id_from_link():
    assert _job_id_from_link(
        "https://careers.nspe.org/jobs/rss/22273101/senior-mechanical-engineer"
    ) == "nspe_22273101"
    # No numeric /jobs/rss/<id>/ segment -> falls back to the raw link, never "".
    assert _job_id_from_link("https://careers.nspe.org/jobs/weird-path") == (
        "nspe_https://careers.nspe.org/jobs/weird-path")
    assert _job_id_from_link("") == ""


# ── parse from fixture ────────────────────────────────────────────────────────
def test_nspe_parse_title_company_location(tmp_path):
    c = _client(tmp_path, industry="mechanical engineering")
    items = _parse_feed(_NSPE_XML)
    out = c.parse_results({"items": items}, "mechanical engineer")
    titles = [j.title for j in out]
    assert "Senior Mechanical Engineer" in titles
    assert "Mechanical Engineer - Discipline Lead" in titles
    j = next(j for j in out if j.title == "Senior Mechanical Engineer")
    assert j.company == "Little"
    assert j.location == "Charlotte, North Carolina"
    assert j.source_api == "nspe"
    assert j.job_id == "nspe_22273101"


def test_nspe_parse_keeps_row_missing_pipe_delimiter(tmp_path):
    # Guard row (item 4): no " | " in title -> kept with company "Unknown",
    # NEVER dropped (inclusion-over-precision design philosophy).
    c = _client(tmp_path, industry="manufacturing")
    out = c.parse_results({"items": _parse_feed(_NSPE_XML)}, "manufacturing engineer")
    row = next(j for j in out if j.title == "Manufacturing Engineer Opening")
    assert row.company == "Unknown"
    assert row.location == "Toledo, Ohio"
    assert row.job_id == "nspe_99999001"


def test_nspe_parse_keeps_row_with_unparseable_location(tmp_path):
    # Item 5: description has no "City, State," prefix -> location="" but the
    # row still survives (never drop for an unparseable location).
    c = _client(tmp_path, industry="industrial engineering")
    out = c.parse_results({"items": _parse_feed(_NSPE_XML)}, "industrial engineer")
    row = next(j for j in out if j.title == "Industrial Engineer")
    assert row.company == "Acme Corp"
    assert row.location == ""
    assert row.job_id == "nspe_99999002"


def test_nspe_parse_matches_broad_keyword(tmp_path):
    c = _client(tmp_path, industry="mechanical engineering")
    out = c.parse_results({"items": _parse_feed(_NSPE_XML)}, "turbomachinery")
    assert [j.title for j in out] == ["Principal Turbomachinery Engineer"]


# ── industry gating ────────────────────────────────────────────────────────────
def test_nspe_industry_gating_mech_mfg_industrial_on():
    assert _terms_for_industry("mechanical engineering")
    assert _terms_for_industry("manufacturing")
    assert _terms_for_industry("industrial engineering")
    assert _terms_for_industry("mechdesign")
    assert _terms_for_industry("cad")


def test_nspe_industry_gating_off_for_other_fields():
    # Nursing (a different sector feed's own gate) must NOT activate NSPE.
    assert _terms_for_industry("nursing") == []
    assert _terms_for_industry("education") == []
    assert _terms_for_industry("welding") == []
    assert _terms_for_industry("") == []      # Alex generic-eng default -> inert
    assert _terms_for_industry(None) == []


def test_nspe_industry_gating_plural_onet_title_activates():
    # PLURAL O*NET occupation titles the wizard persists verbatim must also
    # activate -- the gate is singular-aware (mirrors the RNJobSite/
    # HigherEdJobs scenario finding #2 fix via industry_profile.gate_tokens).
    assert _terms_for_industry("Industrial Engineers")
    assert _terms_for_industry("Mechanical Engineers")


def test_nspe_self_skip_search_returns_empty(tmp_path):
    # A nurse's client fetches nothing (never hits the network -- a monkeypatched
    # session.get would fire an assertion if it did; see the no-network test below).
    c = _client(tmp_path, industry="nursing")
    assert c.terms == []
    assert c.search("nurse", page=1) == {"items": []}


def test_nspe_mech_client_has_terms(tmp_path):
    c = _client(tmp_path, industry="mechanical engineering")
    assert c.terms  # non-empty -> would poll


# ── no-network guarantee when gated off ───────────────────────────────────────
def test_nspe_gated_off_no_network_call_made(tmp_path, monkeypatch):
    c = _client(tmp_path, industry="nursing")

    def _boom(*a, **kw):
        raise AssertionError("nspe.search() must not make an HTTP call "
                              "when gated off (non-mech industry)")
    monkeypatch.setattr(c.session, "get", _boom)
    assert c.search("nurse", page=1) == {"items": []}
    assert c.search("nurse", page=2) == {"items": []}  # page>1 guard too


# ── malformed-XML resilience ───────────────────────────────────────────────────
# Mirrors tests/test_s35_sector_feed_cache_errors.py's shared _BAD_XML fixture
# and per-client contract for the sibling sector feeds.
_BAD_XML = b"<this is not >< valid xml at all"


def test_nspe_parse_feed_raises_on_malformed_xml():
    # A CAPTCHA/maintenance/garbage response must RAISE, not silently return
    # [] -- see search.higheredjobs_client._parse_feed's docstring: the
    # caller's _cached() must skip the cache write on a parse failure (S35
    # finding #5), never cache a false "empty feed" for the TTL.
    with pytest.raises(Exception):
        _parse_feed(_BAD_XML)


def test_nspe_parse_error_not_cached_and_warns(tmp_path, monkeypatch, capsys):
    c = _client(tmp_path, industry="mechanical engineering")
    c.cache_enabled = True

    class _Resp:
        status_code = 200
        content = _BAD_XML

        def raise_for_status(self):
            return None

    monkeypatch.setattr(c.session, "get", lambda *a, **k: _Resp())
    with pytest.raises(Exception):
        c._fetch_term("mechanical")
    assert list(tmp_path.rglob("*.json")) == []   # no cache file written
    out = capsys.readouterr().out
    assert "WARNING" in out and "nspe" in out


def test_nspe_empty_success_is_cached(tmp_path, monkeypatch):
    c = _client(tmp_path, industry="mechanical engineering")
    c.cache_enabled = True

    class _Resp:
        status_code = 200
        content = b'<?xml version="1.0"?><rss version="2.0"><channel><title>N</title></channel></rss>'

        def raise_for_status(self):
            return None

    monkeypatch.setattr(c.session, "get", lambda *a, **k: _Resp())
    items = c._fetch_term("mechanical")
    assert items == []
    assert list(tmp_path.rglob("*.json"))   # a real empty result IS cached


# ── source_taxonomy shim ───────────────────────────────────────────────────────
def test_source_taxonomy_nspe_gate():
    from search import source_taxonomy as st
    assert st.nspe_active("mechanical engineering") is True
    assert st.nspe_active("manufacturing") is True
    assert st.nspe_active("nursing") is False
    assert st.nspe_active("welding") is False
    assert st.sector_feed_applies("nspe", "mechanical engineering") is True
    assert st.sector_feed_applies("nspe", "nursing") is False


# ── registration ──────────────────────────────────────────────────────────────
def test_nspe_registered_in_all_sources():
    from search.cli import ALL_SOURCES
    assert "nspe" in ALL_SOURCES


def test_nspe_registered_in_daily_sources():
    from config import DAILY_SOURCES
    assert "nspe" in DAILY_SOURCES


def test_nspe_registered_in_source_builders():
    from search.source_registry import SOURCE_BUILDERS
    assert "nspe" in SOURCE_BUILDERS


def test_build_clients_nspe_inert_for_non_mech_industry(tmp_path, monkeypatch):
    # A nursing (non-mech) build registers the nspe client but it is inert --
    # no network, no jobs. Mirrors test_build_clients_sector_feeds_inert_for_eng.
    from search.cli import build_clients
    monkeypatch.setattr("config.CACHE_DIR", tmp_path)
    clients = build_clients(["nspe"], cache_enabled=False, industry_filter="nursing")
    by_name = {type(c).__name__: c for c in clients}
    assert by_name["NspeClient"].terms == []


def test_build_clients_nspe_active_for_mech_industry(tmp_path, monkeypatch):
    from search.cli import build_clients
    monkeypatch.setattr("config.CACHE_DIR", tmp_path)
    clients = build_clients(["nspe"], cache_enabled=False,
                            industry_filter="mechanical engineering")
    by_name = {type(c).__name__: c for c in clients}
    assert by_name["NspeClient"].terms  # non-empty -> would poll
