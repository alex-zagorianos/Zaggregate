"""ATS auto-detection from career-page URLs + paste-line parsing."""
from scrape.ats_detect import detect_ats, parse_line


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
    expect = ("workday", "cat:5:CaterpillarCareers")
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
    # A big-employer public careers URL resolves to a scrapable tenant:N:site slug.
    assert detect_ats("https://pg.wd5.myworkdayjobs.com/en-US/PGCareers") == \
        ("workday", "pg:5:PGCareers")


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
