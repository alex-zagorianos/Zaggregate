from scrape.ats_detect import detect_ats
from scrape.company_registry import CompanyEntry
from scrape.careers_client import CareersClient

def test_ats_detect_workable():
    assert detect_ats("https://apply.workable.com/acme/") == ("workable", "acme")

def test_ats_detect_recruitee():
    assert detect_ats("https://beta.recruitee.com/") == ("recruitee", "beta")

def test_ats_detect_personio():
    assert detect_ats("https://acme.jobs.personio.de/") == ("personio", "acme")

def _capture_stub(captured, name):
    """Stub scraper that records the slug + keyword it was forwarded and returns []."""
    def _stub(slug, *, keyword=""):
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
    assert captured["workable"] == {"slug": "acme", "keyword": "engineer"}


def test_dispatch_routes_recruitee(tmp_path, monkeypatch):
    import scrape.careers_client as cc
    captured = {}
    monkeypatch.setattr(cc, "scrape_recruitee", _capture_stub(captured, "recruitee"))
    client = CareersClient(cache_dir=tmp_path, cache_enabled=False, discovery_enabled=False)
    company = CompanyEntry("Beta", "recruitee", "beta", [])
    client._scrape_one(company, "engineer")
    assert captured["recruitee"] == {"slug": "beta", "keyword": "engineer"}


def test_dispatch_routes_rippling(tmp_path, monkeypatch):
    import scrape.careers_client as cc
    captured = {}
    monkeypatch.setattr(cc, "scrape_rippling", _capture_stub(captured, "rippling"))
    client = CareersClient(cache_dir=tmp_path, cache_enabled=False, discovery_enabled=False)
    company = CompanyEntry("Gamma", "rippling", "gamma", [])
    client._scrape_one(company, "engineer")
    assert captured["rippling"] == {"slug": "gamma", "keyword": "engineer"}


def test_dispatch_routes_personio(tmp_path, monkeypatch):
    import scrape.careers_client as cc
    captured = {}
    monkeypatch.setattr(cc, "scrape_personio", _capture_stub(captured, "personio"))
    client = CareersClient(cache_dir=tmp_path, cache_enabled=False, discovery_enabled=False)
    company = CompanyEntry("Delta", "personio", "delta", [])
    client._scrape_one(company, "engineer")
    assert captured["personio"] == {"slug": "delta", "keyword": "engineer"}
