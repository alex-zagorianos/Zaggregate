"""ATS auto-detection from career-page URLs + paste-line parsing."""
import pytest

from scrape.ats_detect import detect_ats, parse_line, resolve_board


def test_greenhouse():
    assert detect_ats("https://boards.greenhouse.io/acme") == ("greenhouse", "acme")
    assert detect_ats("https://job-boards.greenhouse.io/acme/jobs/123") == ("greenhouse", "acme")
    assert detect_ats("boards.greenhouse.io/acme") == ("greenhouse", "acme")  # no scheme
    assert detect_ats("https://boards-api.greenhouse.io/v1/boards/acme/jobs") == ("greenhouse", "acme")


def test_lever():
    assert detect_ats("https://jobs.lever.co/acme") == ("lever", "acme")
    assert detect_ats("https://jobs.lever.co/acme/postings") == ("lever", "acme")


def test_ashby():
    assert detect_ats("https://jobs.ashbyhq.com/acme") == ("ashby", "acme")
    assert detect_ats("https://acme.ashbyhq.com") == ("ashby", "acme")
    assert detect_ats("https://jobs.ashbyhq.com/gecko-robotics") == ("ashby", "gecko-robotics")


def test_smartrecruiters():
    assert detect_ats("https://jobs.smartrecruiters.com/AcmeCorp") == ("smartrecruiters", "AcmeCorp")


def test_workday_public_locale_and_cxs():
    # Newly-pasted Workday URLs now resolve to the public wday/cxs JSON reader
    # (workday_cxs), which POSTs the JSON search body to dodge the HTML/CSRF wall
    # the legacy GET-prime "workday" path hit with HTTP 422. Slug format unchanged.
    expect = ("workday_cxs", "cat:5:CaterpillarCareers")
    assert detect_ats("https://cat.wd5.myworkdayjobs.com/CaterpillarCareers/job/X_R1") == expect
    assert detect_ats("https://cat.wd5.myworkdayjobs.com/en-US/CaterpillarCareers") == expect
    assert detect_ats("https://cat.wd5.myworkdayjobs.com/wday/cxs/cat/CaterpillarCareers/jobs") == expect


def test_direct_fallback():
    ats, slug = detect_ats("https://www.emerson.com/en-us/careers/search-jobs")
    assert ats == "direct" and "emerson.com" in slug


def test_enterprise_ats_icims_taleo_successfactors():
    # No JSON API — tagged for the JSON-LD scraper; slug = the careers URL.
    icims = "https://careers-kroger.icims.com/jobs/search"
    assert detect_ats(icims) == ("icims", icims)
    taleo = "https://ge.taleo.net/careersection/x/jobsearch.ftl"
    assert detect_ats(taleo) == ("taleo", taleo)
    sf = "https://career5.successfactors.com/career?company=acme"
    assert detect_ats(sf) == ("successfactors", sf)


def test_workday_public_pg_tenant():
    # A big-employer public careers URL resolves to a scrapable tenant:N:site slug
    # via the public cxs JSON reader.
    assert detect_ats("https://pg.wd5.myworkdayjobs.com/en-US/PGCareers") == \
        ("workday_cxs", "pg:5:PGCareers")


def test_parse_line_bare_url_derives_name():
    e = parse_line("https://boards.greenhouse.io/pathrobotics")
    assert (e.ats_type, e.slug, e.name) == ("greenhouse", "pathrobotics", "Pathrobotics")


def test_parse_line_name_pipe_url():
    e = parse_line("Path Robotics | https://boards.greenhouse.io/pathrobotics")
    assert (e.name, e.ats_type, e.slug) == ("Path Robotics", "greenhouse", "pathrobotics")


def test_parse_line_power_form():
    e = parse_line("Caterpillar | workday | cat:5:CaterpillarCareers")
    assert (e.ats_type, e.slug) == ("workday", "cat:5:CaterpillarCareers")


def test_parse_line_skips_blank_and_comment():
    assert parse_line("") is None
    assert parse_line("   ") is None
    assert parse_line("# a header line") is None


# ── resolve_board: board-root resolution for browser clip-to-seed (SB-3) ──────
# A clipped *job-posting* URL must resolve back to its board ROOT so the whole
# board (not one job) is seeded. detect_ats already strips the job-id path;
# resolve_board wraps it with a resolvable/unresolvable verdict + a clean name.

@pytest.mark.parametrize("url,ats,slug", [
    # greenhouse posting -> board root
    ("https://boards.greenhouse.io/acme/jobs/4567890", "greenhouse", "acme"),
    ("https://job-boards.greenhouse.io/acme/jobs/4567890", "greenhouse", "acme"),
    # lever posting (uuid, /apply) -> board root
    ("https://jobs.lever.co/acme/12345678-abcd-1234-5678-1234567890ab", "lever", "acme"),
    ("https://jobs.lever.co/acme/12345678-abcd/apply", "lever", "acme"),
    # ashby posting (path form + subdomain form) -> board root
    ("https://jobs.ashbyhq.com/acme/some-job-id", "ashby", "acme"),
    ("https://acme.ashbyhq.com/AcmeCorp/12345", "ashby", "acme"),
    # smartrecruiters posting -> board root
    ("https://jobs.smartrecruiters.com/AcmeCorp/743999-title", "smartrecruiters", "AcmeCorp"),
    # workday public posting -> tenant:N:site (the cxs JSON reader)
    ("https://acme.wd5.myworkdayjobs.com/en-US/AcmeCareers/job/Loc/Title_R-1",
     "workday_cxs", "acme:5:AcmeCareers"),
])
def test_resolve_board_posting_url_resolves_to_board_root(url, ats, slug):
    r = resolve_board(url)
    assert r["resolvable"] is True
    assert r["ats_type"] == ats
    assert r["slug"] == slug


def test_resolve_board_prefers_clean_slug_name_over_noisy_page_title():
    # A posting's <title> is the JOB title with board chrome — using it as the
    # board name would mis-name the board and defeat name-based dedup.
    r = resolve_board("https://boards.greenhouse.io/acme/jobs/1",
                      "Senior Software Engineer - Acme | Greenhouse")
    assert r["name"] == "Acme"


def test_resolve_board_direct_careers_page_is_unresolvable():
    # A generic company careers page is 'direct' — no probeable board, so a
    # one-click clip can't verify it live. Unresolvable (unlike the paste dialog,
    # which treats 'direct' as verified-manual).
    r = resolve_board("https://careers.acme.com/openings")
    assert r["resolvable"] is False
    assert r["ats_type"] == "direct"


@pytest.mark.parametrize("url", [
    "https://www.google.com/search?q=jobs",     # search result, not a board
    "https://en.wikipedia.org/wiki/Cat",         # random page
    "",                                          # empty
])
def test_resolve_board_junk_is_unresolvable(url):
    assert resolve_board(url)["resolvable"] is False


# ---------------------------------------------------------------------------
# probe_board — the reachability verdict (P0-6 fix). A walled workday_cxs tenant
# (HTTP 422) must land UNREACHABLE, not "verified (0 open jobs)"; a genuinely-
# live board with 0 open jobs must land REACHABLE (verified-empty).
# ---------------------------------------------------------------------------
def test_probe_board_direct_is_uncountable_and_not_reachable():
    from scrape.ats_detect import probe_board
    from scrape.company_registry import CompanyEntry
    pr = probe_board(CompanyEntry("Acme", "direct", "https://acme.com/careers"))
    assert pr.count is None and pr.reachable is False


def test_probe_board_workday_cxs_walled_422_is_unreachable(monkeypatch):
    # The exact smoke-test defect: a 422-walled Workday tenant must be UNREACHABLE
    # (count None, reachable False), NOT verified-with-0-jobs.
    from scrape import ats_detect
    from scrape.cache_helpers import STATUS_PERMANENT
    from scrape.company_registry import CompanyEntry
    import scrape.workday_cxs_scraper as WC
    monkeypatch.setattr(WC, "fetch_with_status",
                        lambda slug, **k: ([], STATUS_PERMANENT))
    pr = ats_detect.probe_board(CompanyEntry("FedEx", "workday_cxs", "fedex:5:careers"))
    assert pr.reachable is False and pr.count is None


def test_probe_board_workday_cxs_live_empty_is_reachable(monkeypatch):
    # A genuinely-live board with 0 open jobs (STATUS_OK, empty list) is REACHABLE
    # -> verified-but-empty, count 0.
    from scrape import ats_detect
    from scrape.cache_helpers import STATUS_OK
    from scrape.company_registry import CompanyEntry
    import scrape.workday_cxs_scraper as WC
    monkeypatch.setattr(WC, "fetch_with_status", lambda slug, **k: ([], STATUS_OK))
    pr = ats_detect.probe_board(CompanyEntry("LiveCo", "workday_cxs", "live:1:Ext"))
    assert pr.reachable is True and pr.count == 0


def test_probe_board_workday_cxs_transient_is_unreachable(monkeypatch):
    # A 429/network blip is not a verified read either -> unreachable this pass.
    from scrape import ats_detect
    from scrape.cache_helpers import STATUS_TRANSIENT
    from scrape.company_registry import CompanyEntry
    import scrape.workday_cxs_scraper as WC
    monkeypatch.setattr(WC, "fetch_with_status",
                        lambda slug, **k: ([], STATUS_TRANSIENT))
    pr = ats_detect.probe_board(CompanyEntry("Busy", "workday_cxs", "busy:1:Ext"))
    assert pr.reachable is False and pr.count is None


def test_probe_board_count_ats_reachable_iff_counted(monkeypatch):
    # For a count-API ATS, reachable mirrors "got a real count": a real count
    # (incl. 0 = live-empty) is reachable; None (non-2xx/parse fail) is not.
    from scrape import ats_detect
    from scrape.company_registry import CompanyEntry
    monkeypatch.setattr(ats_detect, "probe_count", lambda e: 0)
    pr = ats_detect.probe_board(CompanyEntry("Gh", "greenhouse", "gh"))
    assert pr.reachable is True and pr.count == 0
    monkeypatch.setattr(ats_detect, "probe_count", lambda e: None)
    pr = ats_detect.probe_board(CompanyEntry("Gh", "greenhouse", "gh"))
    assert pr.reachable is False and pr.count is None


def test_probe_count_workday_cxs_walled_returns_none(monkeypatch):
    # The bare-count contract too: a walled tenant returns None (not a false 0),
    # so any legacy count-only caller can't mistake a wall for a live-empty board.
    from scrape import ats_detect
    from scrape.cache_helpers import STATUS_OK, STATUS_PERMANENT
    from scrape.company_registry import CompanyEntry
    import scrape.workday_cxs_scraper as WC
    monkeypatch.setattr(WC, "fetch_with_status",
                        lambda slug, **k: ([], STATUS_PERMANENT))
    assert ats_detect.probe_count(
        CompanyEntry("FedEx", "workday_cxs", "fedex:5:careers")) is None
    # A clean read with 0 jobs is a real 0 (live-empty).
    monkeypatch.setattr(WC, "fetch_with_status", lambda slug, **k: ([], STATUS_OK))
    assert ats_detect.probe_count(
        CompanyEntry("LiveCo", "workday_cxs", "live:1:Ext")) == 0
