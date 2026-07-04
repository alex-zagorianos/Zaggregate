from scrape.ats_detect import detect_ats
from scrape.company_registry import CompanyEntry
from scrape.careers_client import CareersClient

def test_ats_detect_workable():
    assert detect_ats("https://apply.workable.com/acme/") == ("workable", "acme")

def test_ats_detect_recruitee():
    assert detect_ats("https://beta.recruitee.com/") == ("recruitee", "beta")

def test_ats_detect_personio():
    assert detect_ats("https://acme.jobs.personio.de/") == ("personio", "acme")

def test_ats_detect_bamboohr():
    assert detect_ats("https://acme.bamboohr.com/careers") == ("bamboohr", "acme")

def test_ats_detect_rippling():
    assert detect_ats("https://ats.rippling.com/acme/jobs") == ("rippling", "acme")

def _capture_stub(captured, name):
    """Stub scraper that records the slug + keyword it was forwarded and returns [].
    Accepts (and ignores) the cache_dir/cache_enabled the dispatcher now threads
    through so caching can be wired into these five scrapers.

    NOTE (S35 #24): workable/recruitee/rippling/personio/bamboohr are all
    memoizable ats_types (scrape.careers_client._MEMOIZABLE_ATS_TYPES) --
    _scrape_one now dispatches the underlying scraper ONCE per company with
    keyword="" (a full unfiltered fetch) and re-filters in Python for every
    real keyword, so the stub sees keyword="" regardless of what keyword
    _scrape_one was called with. These tests still verify what they always
    verified: dispatch routes to the right scraper with the right slug."""
    def _stub(slug, *, keyword="", cache_dir=None, cache_enabled=False):
        captured[name] = {"slug": slug, "keyword": keyword}
        return []
    return _stub


def test_dispatch_routes_workable(tmp_path, monkeypatch):
    import scrape.careers_client as cc
    captured = {}
    monkeypatch.setattr(cc, "scrape_workable", _capture_stub(captured, "workable"))
    client = CareersClient(cache_dir=tmp_path, cache_enabled=False, discovery_enabled=False)
    company = CompanyEntry("Acme", "workable", "acme", [])
    client._scrape_one(company, "engineer")
    assert captured["workable"] == {"slug": "acme", "keyword": ""}


def test_dispatch_routes_recruitee(tmp_path, monkeypatch):
    import scrape.careers_client as cc
    captured = {}
    monkeypatch.setattr(cc, "scrape_recruitee", _capture_stub(captured, "recruitee"))
    client = CareersClient(cache_dir=tmp_path, cache_enabled=False, discovery_enabled=False)
    company = CompanyEntry("Beta", "recruitee", "beta", [])
    client._scrape_one(company, "engineer")
    assert captured["recruitee"] == {"slug": "beta", "keyword": ""}


def test_dispatch_routes_rippling(tmp_path, monkeypatch):
    import scrape.careers_client as cc
    captured = {}
    monkeypatch.setattr(cc, "scrape_rippling", _capture_stub(captured, "rippling"))
    client = CareersClient(cache_dir=tmp_path, cache_enabled=False, discovery_enabled=False)
    company = CompanyEntry("Gamma", "rippling", "gamma", [])
    client._scrape_one(company, "engineer")
    assert captured["rippling"] == {"slug": "gamma", "keyword": ""}


def test_dispatch_routes_personio(tmp_path, monkeypatch):
    import scrape.careers_client as cc
    captured = {}
    monkeypatch.setattr(cc, "scrape_personio", _capture_stub(captured, "personio"))
    client = CareersClient(cache_dir=tmp_path, cache_enabled=False, discovery_enabled=False)
    company = CompanyEntry("Delta", "personio", "delta", [])
    client._scrape_one(company, "engineer")
    assert captured["personio"] == {"slug": "delta", "keyword": ""}


def test_dispatch_routes_bamboohr(tmp_path, monkeypatch):
    import scrape.careers_client as cc
    captured = {}
    monkeypatch.setattr(cc, "scrape_bamboohr", _capture_stub(captured, "bamboohr"))
    client = CareersClient(cache_dir=tmp_path, cache_enabled=False, discovery_enabled=False)
    company = CompanyEntry("Epsilon", "bamboohr", "epsilon", [])
    client._scrape_one(company, "engineer")
    assert captured["bamboohr"] == {"slug": "epsilon", "keyword": ""}
