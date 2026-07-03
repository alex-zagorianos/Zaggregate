"""Vincere quick-job-board scraper (S34).

Fixture-based, network-free (mirrors tests/test_workday_cxs.py): the shared
careers_session .get/.post are patched via _scrape_fakes.patch_session, so the
landing-page GET (mints the CSRF token) and the ajax POST (returns the jobs JSON)
are both served from in-process fixtures with no network and no rate-limit sleeps.

Contract discovered live 2026-07-02 against careers.edisonsmart.com (214 jobs):
  GET  {host}/                  -> HTML with a Laravel _token + static.vincere.io
                                   fingerprint (+ sets session cookies)
  POST {host}/ajax/search-jobs  (form: _token, keywords, page, ...) -> 200 JSON
      {"total": T, "more": bool, "items": [ {job}, ... ]}
Each item: id / job_title / location{...} / salary_from/to / published_date /
close_date / public_description (HTML). Job URL = {host}/job/{id}/{slug}.
"""
import pytest

from scrape import vincere_scraper as V
from scrape.ats_detect import (ProbeResult, detect_ats, is_tos_blocked_host,
                               probe_board, probe_count, resolve_board)
from scrape.company_registry import CompanyEntry
from tests.scrape._scrape_fakes import FakeResp, patch_session


# --- fixtures -----------------------------------------------------------------
_HOST = "careers.edisonsmart.com"

_PAGE_HTML = (
    '<!doctype html><html><head>'
    '<link rel="icon" href="https://static.vincere.io/img/qjb-fav.png">'
    '<img src="https://static.vincere.io/quick-job-board/edison-search-vincere-io/'
    'image/abc/Logo.png">'
    '</head><body>'
    '<form class="js-search-form" method="post" action="/ajax/search-jobs">'
    '<input type="hidden" name="_token" value="TESTTOKEN123">'
    '</form></body></html>'
)

# A generic (non-Vincere) careers page: no static.vincere.io asset.
_PLAIN_HTML = ('<!doctype html><html><head><title>Careers</title></head>'
               '<body><form><input name="_token" value="X"></form></body></html>')


def _item(jid, title, *, city="London", state="", country="United Kingdom",
          country_code="GB", salary_from="0.0", salary_to="0.0",
          published="2026-07-01T10:00:00.000Z", close="", desc="<p>Build things.</p>"):
    return {
        "id": jid,
        "job_title": title,
        "location": {"address": f"{city}, {country}", "city": city, "state": state,
                     "country": country, "country_code": country_code,
                     "location_name": f"{state or city}"},
        "salary_from": salary_from, "salary_to": salary_to, "salary_type": "ANNUAL",
        "formatted_salary_from": "", "formatted_salary_to": "",
        "published_date": published, "open_date": None, "close_date": close,
        "job_type": "PERMANENT", "employment_type": "FULL_TIME",
        "public_description": desc,
    }


def _ajax_page(items, *, total, more):
    return {"total": total, "more": more, "items": items,
            "facets": {}, "html": "<article>...</article>"}


def _handler(pages, *, page_html=_PAGE_HTML):
    """Build a patch_session handler: a GET returns the landing HTML; a POST to
    the ajax endpoint returns pages[<page>] (a dict already JSON-shaped, or a
    FakeResp for error cases). ``pages`` maps page-number -> ajax body dict."""
    def _h(url, *a, **k):
        # patch_session routes both .get and .post here; distinguish by presence
        # of a form 'data' payload (the POST) vs a bare GET.
        data = k.get("data")
        if data is None:
            # landing-page GET
            return FakeResp(text=page_html)
        page = int(data.get("page", 1))
        body = pages.get(page)
        if isinstance(body, FakeResp):
            return body
        return FakeResp(body)
    return _h


# --- parse / map --------------------------------------------------------------
def test_maps_items_to_jobresults(monkeypatch, tmp_path):
    pages = {1: _ajax_page(
        [_item(252557, "Senior Client Platform Engineer", state="NJ",
               country="United States", country_code="US",
               salary_from="120000.0", salary_to="150000.0",
               close="2026-09-01", desc="<p>Ship <b>React</b> apps.</p>")],
        total=1, more=False)}
    patch_session(monkeypatch, V, _handler(pages))
    jobs = V.fetch(_HOST, keyword="", company_name="Edison Smart",
                   cache_dir=tmp_path, cache_enabled=False)
    assert len(jobs) == 1
    j = jobs[0]
    assert j.title == "Senior Client Platform Engineer"
    assert j.company == "Edison Smart"          # registry display name wins
    assert j.location in ("NJ", "New Jersey, United States")  # location_name/address
    assert j.salary_min == 120000.0 and j.salary_max == 150000.0
    assert j.source_api == "careers"
    assert j.board_count == 1
    assert j.created == "2026-07-01T10:00:00.000Z"
    assert j.valid_through == "2026-09-01"      # close_date -> publisher expiry
    assert j.description == "Ship React apps."   # HTML stripped
    assert j.job_id == "vincere_careers.edisonsmart.com_252557"
    assert j.url == ("https://careers.edisonsmart.com/job/252557/"
                     "senior-client-platform-engineer")


def test_zero_salary_is_unset(monkeypatch, tmp_path):
    pages = {1: _ajax_page([_item(1, "Analyst")], total=1, more=False)}
    patch_session(monkeypatch, V, _handler(pages))
    j = V.fetch(_HOST, cache_dir=tmp_path, cache_enabled=False)[0]
    assert j.salary_min is None and j.salary_max is None   # "0.0" -> None


def test_display_name_from_host_when_no_registry_name(monkeypatch, tmp_path):
    pages = {1: _ajax_page([_item(1, "Analyst")], total=1, more=False)}
    patch_session(monkeypatch, V, _handler(pages))
    j = V.fetch(_HOST, company_name="", cache_dir=tmp_path, cache_enabled=False)[0]
    assert j.company == "Edisonsmart"           # careers.edisonsmart.com -> Edisonsmart


# --- pagination ---------------------------------------------------------------
def test_paginates_until_more_false(monkeypatch, tmp_path):
    pages = {
        1: _ajax_page([_item(i, f"Role {i}") for i in range(1, 11)], total=25, more=True),
        2: _ajax_page([_item(i, f"Role {i}") for i in range(11, 21)], total=25, more=True),
        3: _ajax_page([_item(i, f"Role {i}") for i in range(21, 26)], total=25, more=False),
    }
    patch_session(monkeypatch, V, _handler(pages))
    jobs = V.fetch(_HOST, cache_dir=tmp_path, cache_enabled=False)
    assert len(jobs) == 25
    assert jobs[0].board_count == 25            # first page's total is authoritative


def test_pagination_stops_on_empty_items(monkeypatch, tmp_path):
    pages = {
        1: _ajax_page([_item(1, "A")], total=5, more=True),
        2: _ajax_page([], total=5, more=True),   # empty chunk -> stop
    }
    patch_session(monkeypatch, V, _handler(pages))
    jobs = V.fetch(_HOST, cache_dir=tmp_path, cache_enabled=False)
    assert len(jobs) == 1


# --- keyword filter (local, whole-board fetch) --------------------------------
def test_local_keyword_filter(monkeypatch, tmp_path):
    pages = {1: _ajax_page(
        [_item(1, "Data Engineer", desc="python etl"),
         _item(2, "Marketing Manager", desc="brand"),
         _item(3, "Sales Rep", desc="based in Engineering district")],
        total=3, more=False)}
    patch_session(monkeypatch, V, _handler(pages))
    jobs = V.fetch(_HOST, keyword="engineer", cache_dir=tmp_path, cache_enabled=False)
    titles = {j.title for j in jobs}
    assert "Data Engineer" in titles            # title hit
    assert "Sales Rep" in titles                # body hit ("Engineering district")
    assert "Marketing Manager" not in titles


# --- reachability status classes ----------------------------------------------
def test_ajax_4xx_first_page_is_permanent(monkeypatch, tmp_path):
    pages = {1: FakeResp(None, status_code=404)}
    patch_session(monkeypatch, V, _handler(pages))
    jobs, status = V.fetch_with_status(_HOST, cache_dir=tmp_path, cache_enabled=False)
    assert jobs == [] and status == V.STATUS_PERMANENT


def test_landing_page_4xx_is_permanent(monkeypatch, tmp_path):
    def _h(url, *a, **k):
        return FakeResp(None, status_code=410)   # GET the page -> gone
    patch_session(monkeypatch, V, _h)
    jobs, status = V.fetch_with_status(_HOST, cache_dir=tmp_path, cache_enabled=False)
    assert jobs == [] and status == V.STATUS_PERMANENT


def test_missing_csrf_token_is_transient(monkeypatch, tmp_path):
    # Landing page without a _token -> can't POST -> transient (page-shape change),
    # not a permanent wall.
    patch_session(monkeypatch, V, _handler({}, page_html="<html><body>no token</body></html>"))
    jobs, status = V.fetch_with_status(_HOST, cache_dir=tmp_path, cache_enabled=False)
    assert jobs == [] and status == V.STATUS_TRANSIENT


def test_live_empty_board_is_ok(monkeypatch, tmp_path):
    pages = {1: _ajax_page([], total=0, more=False)}
    patch_session(monkeypatch, V, _handler(pages))
    jobs, status = V.fetch_with_status(_HOST, cache_dir=tmp_path, cache_enabled=False)
    assert jobs == [] and status == V.STATUS_OK   # verified-empty, not a wall


# --- fingerprint detection ----------------------------------------------------
def test_looks_like_vincere_fingerprint():
    assert V.looks_like_vincere(_PAGE_HTML) is True
    assert V.looks_like_vincere(_PLAIN_HTML) is False
    assert V.looks_like_vincere("") is False


def test_is_vincere_host_probes_html(monkeypatch, tmp_path):
    patch_session(monkeypatch, V, _handler({}))          # GET returns _PAGE_HTML
    assert V.is_vincere_host("https://careers.edisonsmart.com/") is True


def test_is_vincere_host_false_on_plain_page(monkeypatch):
    patch_session(monkeypatch, V, _handler({}, page_html=_PLAIN_HTML))
    assert V.is_vincere_host("https://careers.other.com/") is False


def test_derive_slug_strips_query_noise():
    noisy = "https://careers.edisonsmart.com/?unit=mile&radius=50&schedule=daily&page=1&search=1"
    assert V.derive_slug(noisy) == "careers.edisonsmart.com"
    posting = "https://careers.edisonsmart.com/job/252557/senior-engineer"
    assert V.derive_slug(posting) == "careers.edisonsmart.com"


# --- resolve_board on the noisy Alex URL (injected probe) ----------------------
def test_resolve_board_resolves_noisy_vincere_url():
    noisy = "https://careers.edisonsmart.com/?unit=mile&radius=50&schedule=daily&page=1&search=1"
    board = resolve_board(noisy, vincere_probe=lambda u: True)
    assert board["resolvable"] is True
    assert board["ats_type"] == "vincere"
    assert board["slug"] == "careers.edisonsmart.com"
    assert board["name"] == "Edisonsmart"


def test_resolve_board_non_vincere_stays_direct_unresolvable():
    board = resolve_board("https://careers.generic.com/openings",
                          vincere_probe=lambda u: False)
    assert board["resolvable"] is False
    assert board["ats_type"] == "direct"


def test_detect_ats_alone_cannot_identify_vincere():
    # Host-only detection can't name Vincere (no ATS-owned host) -> direct.
    ats, slug = detect_ats("https://careers.edisonsmart.com/")
    assert ats == "direct"


def test_tos_blocked_host_never_probed_for_vincere():
    # A ToS-blocked host must never resolve to vincere even if the probe would
    # say yes — the guard short-circuits before probing.
    called = []
    board = resolve_board("https://www.indeed.com/jobs?q=x",
                          vincere_probe=lambda u: called.append(u) or True)
    assert board["ats_type"] == "direct" and board["resolvable"] is False
    assert called == []                          # probe never ran
    assert is_tos_blocked_host("https://www.indeed.com/jobs") is True


# --- probe_board / probe_count via the fetcher --------------------------------
def test_probe_board_reads_live_count(monkeypatch, tmp_path):
    pages = {1: _ajax_page([_item(1, "A"), _item(2, "B")], total=2, more=False)}
    patch_session(monkeypatch, V, _handler(pages))
    pr = probe_board(CompanyEntry("Edison Smart", "vincere", _HOST))
    assert isinstance(pr, ProbeResult)
    assert pr.reachable is True and pr.count == 2


def test_probe_board_walled_is_unreachable(monkeypatch):
    patch_session(monkeypatch, V, _handler({1: FakeResp(None, status_code=404)}))
    pr = probe_board(CompanyEntry("Edison Smart", "vincere", _HOST))
    assert pr.reachable is False and pr.count is None


def test_probe_count_vincere(monkeypatch):
    pages = {1: _ajax_page([_item(1, "A")], total=1, more=False)}
    patch_session(monkeypatch, V, _handler(pages))
    assert probe_count(CompanyEntry("Edison Smart", "vincere", _HOST)) == 1


# --- robots gate --------------------------------------------------------------
def test_robots_disallow_skips_board(monkeypatch, tmp_path):
    # robots.txt Disallows the ajax path -> skip with PERMANENT, never POST.
    monkeypatch.setattr(V, "_robots_ok", lambda host: False)
    posted = []
    monkeypatch.setattr(V, "_get_page_html",
                        lambda host: posted.append(host) or (_PAGE_HTML, V.STATUS_OK))
    jobs, status = V.fetch_with_status(_HOST, cache_dir=tmp_path, cache_enabled=False)
    assert jobs == [] and status == V.STATUS_PERMANENT
    assert posted == []                          # bailed before even the GET
