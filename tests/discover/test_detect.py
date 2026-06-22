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
