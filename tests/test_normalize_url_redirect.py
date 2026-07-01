"""Plan 2 — normalize_url unwraps redirect wrappers + collapses Indeed jk, so a
click-redirect and the direct ATS/Indeed URL dedup to ONE posting."""
from models import normalize_url


def test_indeed_variants_collapse_to_jk():
    canon = "indeed.com/viewjob?jk=abcd1234"
    assert normalize_url("https://www.indeed.com/viewjob?jk=abcd1234") == canon
    assert normalize_url("https://www.indeed.com/rc/clk?jk=abcd1234&fccid=x&vjs=3") == canon
    assert normalize_url("https://www.indeed.com/m/viewjob?jk=abcd1234") == canon
    assert normalize_url("https://uk.indeed.com/viewjob?jk=abcd1234&from=serp") == canon


def test_google_redirect_unwraps_to_destination():
    direct = "https://boards.greenhouse.io/acme/jobs/123"
    wrapped = "https://www.google.com/url?q=" + direct + "&sa=D&usg=xyz"
    assert normalize_url(wrapped) == normalize_url(direct)


def test_generic_redirect_param_unwraps():
    direct = "https://jobs.lever.co/acme/abc-123"
    wrapped = "https://track.example.com/click?url=" + direct + "&aff=42"
    assert normalize_url(wrapped) == normalize_url(direct)


def test_non_redirect_urls_unchanged():
    # A normal ATS URL is untouched by the new unwrap/indeed logic (BC).
    assert normalize_url("https://boards.greenhouse.io/acme/jobs/9?gh_jid=9") == \
        "boards.greenhouse.io/acme/jobs/9?gh_jid=9"
    # A query param literally named 'url' that isn't an http destination stays put.
    assert normalize_url("https://x.com/p?url=notaurl") == "x.com/p?url=notaurl"


def test_redirect_and_direct_dedup_via_resolve():
    # End-to-end: the coverage resolver collapses the pair to one cluster.
    import json
    from models import JobResult
    from coverage.resolve import resolve
    direct = "https://boards.greenhouse.io/acme/jobs/123"
    wrapped = "https://www.google.com/url?q=" + direct
    a = JobResult("Controls Engineer", "Acme", "Cincinnati, OH", None, None, "",
                  direct, "controls", "", job_id="a")
    b = JobResult("Controls Engineer", "Acme", "Cincinnati, OH", None, None, "",
                  wrapped, "controls", "", job_id="b")
    assert len(resolve([a, b])) == 1
