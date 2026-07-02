from discover.detect import detect_ats

def test_greenhouse_url():
    assert detect_ats("https://boards.greenhouse.io/acme") == ("greenhouse", "acme")

def test_workable_host_inspect():
    assert detect_ats("https://apply.workable.com/acme/") == ("workable", "acme")

def test_recruitee_subdomain():
    assert detect_ats("https://acme.recruitee.com/") == ("recruitee", "acme")

def test_personio_subdomain():
    assert detect_ats("https://acme.jobs.personio.de/") == ("personio", "acme")

def test_unknown_returns_none():
    assert detect_ats("https://example.com/about") is None

def test_empty_returns_none():
    assert detect_ats("") is None

def test_workday_public_url_resolves():
    # Public Workday URLs now resolve to the wday/cxs JSON reader (workday_cxs).
    assert detect_ats("https://pg.wd5.myworkdayjobs.com/en-US/PGCareers") == \
        ("workday_cxs", "pg:5:PGCareers")

def test_enterprise_jsonld_boards_pass_through():
    # icims/taleo/successfactors slugs are URLs (dots/slashes) — they must NOT be
    # rejected by the board-slug validator meant for greenhouse/lever ids.
    icims = "https://careers-kroger.icims.com/jobs/search"
    assert detect_ats(icims) == ("icims", icims)
    taleo = "https://ge.taleo.net/careersection/x/jobsearch.ftl"
    assert detect_ats(taleo) == ("taleo", taleo)
    sf = "https://career5.successfactors.com/career?company=acme"
    assert detect_ats(sf) == ("successfactors", sf)
