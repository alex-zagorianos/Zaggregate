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
