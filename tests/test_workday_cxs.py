"""Workday `wday/cxs` public-JSON fetcher (S32 marquee-employer unlock).

Mirrors the tests/test_careers_fixes.py style: fixture-based parse/map, keyword
filter, pagination stop, dispatch registration, and fail-soft on 422/404/junk.

The fetcher POSTs the public CXS search body (the read path that dodges the
HTML/CSRF wall) and routes through the shared careers_session + per-host limiter,
so the fake-session helper patches both (no network, no real rate-limit sleeps).
Fixture below is trimmed from a real mmc.wd1 / nvidia.wd5 response captured live
2026-07-02.
"""
import requests

from scrape import workday_cxs_scraper as WC
from scrape.ats_detect import detect_ats, parse_line
from scrape.company_registry import CompanyEntry
from tests.scrape._scrape_fakes import FakeResp, patch_session


# --- a real (trimmed) CXS page: title / externalPath / locationsText / postedOn
#     / bulletFields[0] = reqId. `total` is the whole-board count. -------------
def _cxs_page(total=2000):
    return {
        "total": total,
        "userAuthenticated": False,
        "jobPostings": [
            {
                "title": "Senior Consultant - Customer Service",
                "externalPath": "/job/Bengaluru---Rockline/Senior-Consultant---Customer-Service_R_341911",
                "locationsText": "Bengaluru - Rockline",
                "postedOn": "Posted Today",
                "bulletFields": ["R_341911"],
            },
            {
                "title": "Autoplan Specialist",
                "externalPath": "/job/Vancouver---Burrard/Autoplan-Specialist_R_353099",
                "locationsText": "Vancouver - Burrard",
                "postedOn": "Posted 5 Days Ago",
                "bulletFields": ["R_353099"],
            },
        ],
    }


# ---------------------------------------------------------------------------
# parse / map
# ---------------------------------------------------------------------------
def test_maps_postings_to_jobresults(tmp_path, monkeypatch):
    patch_session(monkeypatch, WC, lambda *a, **k: FakeResp(_cxs_page()))
    jobs = WC.fetch("mmc:1:MMC", keyword="", company_name="Marsh McLennan",
                    cache_dir=tmp_path, cache_enabled=False)
    assert len(jobs) == 2
    j = jobs[0]
    assert j.title == "Senior Consultant - Customer Service"
    assert j.company == "Marsh McLennan"          # registry display name, not "Mmc"
    assert j.location == "Bengaluru - Rockline"
    assert j.source_api == "careers"
    assert j.job_id == "workdaycxs_mmc_R_341911"  # reqId from bulletFields[0]
    assert j.created == "Posted Today"            # relative label passed through
    assert j.board_count == 2000                  # whole-board total, not page len
    # Public posting URL = host + site + externalPath (site inserted).
    assert j.url == ("https://mmc.wd1.myworkdayjobs.com/MMC/job/"
                     "Bengaluru---Rockline/Senior-Consultant---Customer-Service_R_341911")


def test_display_name_falls_back_to_tenant(tmp_path, monkeypatch):
    patch_session(monkeypatch, WC, lambda *a, **k: FakeResp(_cxs_page()))
    jobs = WC.fetch("mmc:1:MMC", keyword="", company_name="",
                    cache_dir=tmp_path, cache_enabled=False)
    assert jobs and all(j.company == "Mmc" for j in jobs)  # title-cased tenant


def test_job_url_does_not_double_insert_site(tmp_path, monkeypatch):
    page = {"total": 1, "jobPostings": [{
        "title": "Controls Engineer",
        # externalPath already carries the site segment -> no re-insert.
        "externalPath": "/CaterpillarCareers/job/Seguin/Controls-Engineer_R1",
        "locationsText": "Seguin, TX", "postedOn": "Posted Today",
        "bulletFields": ["R1"]}]}
    patch_session(monkeypatch, WC, lambda *a, **k: FakeResp(page))
    jobs = WC.fetch("cat:5:CaterpillarCareers", cache_dir=tmp_path, cache_enabled=False)
    assert jobs[0].url == ("https://cat.wd5.myworkdayjobs.com/CaterpillarCareers/"
                           "job/Seguin/Controls-Engineer_R1")


# ---------------------------------------------------------------------------
# keyword filter (title + locationsText, no description on the list endpoint)
# ---------------------------------------------------------------------------
def test_keyword_filter_on_title(tmp_path, monkeypatch):
    patch_session(monkeypatch, WC, lambda *a, **k: FakeResp(_cxs_page()))
    jobs = WC.fetch("mmc:1:MMC", keyword="consultant",
                    cache_dir=tmp_path, cache_enabled=False)
    assert [j.title for j in jobs] == ["Senior Consultant - Customer Service"]


def test_keyword_matches_location_token(tmp_path, monkeypatch):
    # A location-token keyword still filters (locationsText is in the haystack).
    patch_session(monkeypatch, WC, lambda *a, **k: FakeResp(_cxs_page()))
    jobs = WC.fetch("mmc:1:MMC", keyword="vancouver",
                    cache_dir=tmp_path, cache_enabled=False)
    assert [j.title for j in jobs] == ["Autoplan Specialist"]


# ---------------------------------------------------------------------------
# pagination — stop on a short (< _PAGE) page
# ---------------------------------------------------------------------------
def test_paginates_until_short_page(tmp_path, monkeypatch):
    calls = {"n": 0}

    def pager(url, **k):
        offset = (k.get("json") or {}).get("offset", 0)
        calls["n"] += 1
        if offset == 0:
            # A full first page (_PAGE postings) + a total that implies more.
            posts = [{"title": f"Engineer {i}",
                      "externalPath": f"/job/x/E{i}_R{i}",
                      "locationsText": "TX", "postedOn": "Posted Today",
                      "bulletFields": [f"R{i}"]} for i in range(WC._PAGE)]
            return FakeResp({"total": WC._PAGE + 1, "jobPostings": posts})
        # Second page: one posting (short page -> paging stops here).
        return FakeResp({"total": WC._PAGE + 1, "jobPostings": [{
            "title": "Engineer last", "externalPath": "/job/x/last_Rlast",
            "locationsText": "TX", "postedOn": "Posted Today",
            "bulletFields": ["Rlast"]}]})

    patch_session(monkeypatch, WC, pager)
    jobs = WC.fetch("acme:1:External", keyword="engineer",
                    cache_dir=tmp_path, cache_enabled=False)
    assert calls["n"] == 2                      # exactly two pages fetched
    assert len(jobs) == WC._PAGE + 1
    assert any(j.title == "Engineer last" for j in jobs)


def test_first_page_total_survives_later_zero(tmp_path, monkeypatch):
    # Some tenants return total=0 on offset>0 pages; the first page's total wins
    # so board_count is not clobbered to 0.
    def pager(url, **k):
        offset = (k.get("json") or {}).get("offset", 0)
        if offset == 0:
            posts = [{"title": f"Engineer {i}", "externalPath": f"/job/x/E{i}_R{i}",
                      "locationsText": "TX", "postedOn": "", "bulletFields": [f"R{i}"]}
                     for i in range(WC._PAGE)]
            return FakeResp({"total": 999, "jobPostings": posts})
        return FakeResp({"total": 0, "jobPostings": [{
            "title": "Engineer last", "externalPath": "/job/x/last_Rlast",
            "locationsText": "TX", "postedOn": "", "bulletFields": ["Rlast"]}]})

    patch_session(monkeypatch, WC, pager)
    jobs = WC.fetch("acme:1:External", cache_dir=tmp_path, cache_enabled=False)
    assert all(j.board_count == 999 for j in jobs)


# ---------------------------------------------------------------------------
# fail-soft: bad slug / permanent 422+404 (negative-cache) / transient
# ---------------------------------------------------------------------------
def test_bad_slug_is_soft(tmp_path):
    assert WC.fetch("not-a-slug", cache_dir=tmp_path, cache_enabled=False) == []
    assert WC.fetch("tenant:x:site", cache_dir=tmp_path, cache_enabled=False) == []  # n not a digit


def test_permanent_422_negative_caches(tmp_path, monkeypatch):
    # 422 = the CSRF/bot wall (FedEx/Banner/AutoZone). PERMANENT -> negative-cache
    # so the run doesn't re-probe a walled tenant every day for a week.
    from scrape.cache_helpers import is_failed, read_cache
    calls = {"n": 0}

    def walled(url, **k):
        calls["n"] += 1
        return FakeResp(None, status_code=422)

    patch_session(monkeypatch, WC, walled)
    assert WC.fetch("fedex:5:fedexcareers", keyword="driver",
                    cache_dir=tmp_path, cache_enabled=True) == []
    assert calls["n"] == 1
    markers = list(tmp_path.glob("workdaycxs_*_FAILED.json"))
    assert len(markers) == 1
    assert is_failed(read_cache(markers[0])) is True
    # Second call sees the marker and does NOT re-fetch.
    assert WC.fetch("fedex:5:fedexcareers", keyword="driver",
                    cache_dir=tmp_path, cache_enabled=True) == []
    assert calls["n"] == 1


def test_permanent_404_negative_caches(tmp_path, monkeypatch):
    from scrape.cache_helpers import is_failed, read_cache
    patch_session(monkeypatch, WC, lambda *a, **k: FakeResp(None, status_code=404))
    assert WC.fetch("deadwd:1:External", cache_dir=tmp_path, cache_enabled=True) == []
    assert any(is_failed(read_cache(p)) for p in tmp_path.glob("workdaycxs_*_FAILED.json"))


def test_transient_does_not_negative_cache(tmp_path, monkeypatch):
    # 429/5xx/network blip must NOT poison a live board for a week.
    patch_session(monkeypatch, WC, lambda *a, **k: FakeResp(None, status_code=429))
    assert WC.fetch("busywd:1:External", cache_dir=tmp_path, cache_enabled=True) == []
    assert list(tmp_path.glob("workdaycxs_*_FAILED.json")) == []

    def boom(*a, **k):
        raise requests.ConnectionError("blip")

    patch_session(monkeypatch, WC, boom)
    assert WC.fetch("busywd:1:External", cache_dir=tmp_path, cache_enabled=True) == []
    assert list(tmp_path.glob("workdaycxs_*_FAILED.json")) == []


def test_junk_body_is_soft(tmp_path, monkeypatch):
    # A 200 whose body is not the expected dict -> no crash, empty result.
    patch_session(monkeypatch, WC, lambda *a, **k: FakeResp(["unexpected", "list"]))
    assert WC.fetch("acme:1:External", cache_dir=tmp_path, cache_enabled=False) == []


# ---------------------------------------------------------------------------
# fetch_with_status — the reachability signal that keeps a walled tenant out of
# the "verified" bucket (the P0-6 verdict fix). A clean 200 read (even empty) is
# STATUS_OK; a 422/404 wall is STATUS_PERMANENT; a 429/network blip is TRANSIENT.
# ---------------------------------------------------------------------------
def test_fetch_with_status_live_ok(tmp_path, monkeypatch):
    from scrape.cache_helpers import STATUS_OK
    patch_session(monkeypatch, WC, lambda *a, **k: FakeResp(_cxs_page()))
    jobs, status = WC.fetch_with_status("mmc:1:MMC", cache_dir=tmp_path,
                                        cache_enabled=False)
    assert status == STATUS_OK and len(jobs) == 2


def test_fetch_with_status_live_but_empty_is_ok(tmp_path, monkeypatch):
    # A genuinely-live board with 0 open jobs (HTTP 200, empty jobPostings) is
    # STATUS_OK with an empty list — a VERIFIED-empty state, NOT unreachable.
    from scrape.cache_helpers import STATUS_OK
    patch_session(monkeypatch, WC,
                  lambda *a, **k: FakeResp({"total": 0, "jobPostings": []}))
    jobs, status = WC.fetch_with_status("live0:1:External", cache_dir=tmp_path,
                                        cache_enabled=False)
    assert status == STATUS_OK and jobs == []


def test_fetch_with_status_walled_422_is_permanent(tmp_path, monkeypatch):
    # The Cloudflare/Akamai wall (FedEx/AutoZone/Nike) returns 422 -> PERMANENT.
    from scrape.cache_helpers import STATUS_PERMANENT
    patch_session(monkeypatch, WC,
                  lambda *a, **k: FakeResp(None, status_code=422))
    jobs, status = WC.fetch_with_status("fedex:5:fedexcareers", cache_dir=tmp_path,
                                        cache_enabled=False)
    assert status == STATUS_PERMANENT and jobs == []


def test_fetch_with_status_404_is_permanent(tmp_path, monkeypatch):
    from scrape.cache_helpers import STATUS_PERMANENT
    patch_session(monkeypatch, WC, lambda *a, **k: FakeResp(None, status_code=404))
    _jobs, status = WC.fetch_with_status("dead:1:External", cache_dir=tmp_path,
                                         cache_enabled=False)
    assert status == STATUS_PERMANENT


def test_fetch_with_status_transient_is_transient(tmp_path, monkeypatch):
    from scrape.cache_helpers import STATUS_TRANSIENT
    patch_session(monkeypatch, WC, lambda *a, **k: FakeResp(None, status_code=429))
    _jobs, status = WC.fetch_with_status("busy:1:External", cache_dir=tmp_path,
                                         cache_enabled=False)
    assert status == STATUS_TRANSIENT


def test_fetch_with_status_bad_slug_is_permanent(tmp_path):
    from scrape.cache_helpers import STATUS_PERMANENT
    jobs, status = WC.fetch_with_status("not-a-slug", cache_dir=tmp_path,
                                        cache_enabled=False)
    assert status == STATUS_PERMANENT and jobs == []


def test_fetch_with_status_negative_cache_stays_permanent(tmp_path, monkeypatch):
    # Once a walled tenant is negative-cached, a re-probe within the TTL must keep
    # returning STATUS_PERMANENT (not flip to a verified-empty STATUS_OK) without
    # re-hitting the network.
    from scrape.cache_helpers import STATUS_PERMANENT
    calls = {"n": 0}

    def walled(url, **k):
        calls["n"] += 1
        return FakeResp(None, status_code=422)

    patch_session(monkeypatch, WC, walled)
    _j1, s1 = WC.fetch_with_status("fedex:5:fedexcareers", cache_dir=tmp_path,
                                   cache_enabled=True)
    _j2, s2 = WC.fetch_with_status("fedex:5:fedexcareers", cache_dir=tmp_path,
                                   cache_enabled=True)
    assert s1 == STATUS_PERMANENT and s2 == STATUS_PERMANENT
    assert calls["n"] == 1                       # second call served from neg-cache


# ---------------------------------------------------------------------------
# derive_slug — URL -> tenant:N:site
# ---------------------------------------------------------------------------
def test_derive_slug_from_public_and_cxs_urls():
    assert WC.derive_slug("https://cat.wd5.myworkdayjobs.com/en-US/CaterpillarCareers") == "cat:5:CaterpillarCareers"
    assert WC.derive_slug("https://mmc.wd1.myworkdayjobs.com/MMC") == "mmc:1:MMC"
    assert WC.derive_slug("https://mmc.wd1.myworkdayjobs.com/wday/cxs/mmc/MMC/jobs") == "mmc:1:MMC"
    assert WC.derive_slug("nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite/job/x_R1") == "nvidia:5:NVIDIAExternalCareerSite"
    assert WC.derive_slug("https://boards.greenhouse.io/acme") == ""   # not Workday
    assert WC.derive_slug("") == ""


# ---------------------------------------------------------------------------
# detection + dispatch registration
# ---------------------------------------------------------------------------
def test_detect_workday_url_is_cxs():
    ats, slug = detect_ats("https://mmc.wd1.myworkdayjobs.com/en-US/MMC")
    assert ats == "workday_cxs"
    assert slug == "mmc:1:MMC"


def test_parse_line_names_workday_cxs():
    e = parse_line("https://cat.wd5.myworkdayjobs.com/CaterpillarCareers")
    assert e.ats_type == "workday_cxs"
    assert e.slug == "cat:5:CaterpillarCareers"
    assert e.name == "Cat"   # tenant title-cased when no name is given


def test_dispatch_routes_workday_cxs(tmp_path, monkeypatch):
    # careers_client routes ats_type == "workday_cxs" to the cxs fetcher, passing
    # the slug + the registry display name. workday_cxs is a memoizable ats_type
    # (S35 #24): _scrape_one dispatches it ONCE per company with keyword="" and
    # re-filters in Python, so the underlying scraper always sees keyword="".
    import scrape.careers_client as cc
    captured = {}

    def stub(slug, *, keyword, cache_dir, cache_enabled, company_name):
        captured.update(slug=slug, keyword=keyword, company_name=company_name)
        return []

    monkeypatch.setattr(cc, "scrape_workday_cxs", stub)
    client = cc.CareersClient(cache_dir=tmp_path, cache_enabled=False,
                              discovery_enabled=False)
    company = CompanyEntry("Marsh McLennan", "workday_cxs", "mmc:1:MMC")
    client._scrape_one(company, "consultant")
    assert captured["slug"] == "mmc:1:MMC"
    assert captured["keyword"] == ""
    assert captured["company_name"] == "Marsh McLennan"
