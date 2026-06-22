from scrape.ats_detect import detect_ats
from scrape.company_registry import CompanyEntry
from scrape.careers_client import CareersClient

def test_ats_detect_workable():
    assert detect_ats("https://apply.workable.com/acme/") == ("workable", "acme")

def test_ats_detect_recruitee():
    assert detect_ats("https://beta.recruitee.com/") == ("recruitee", "beta")

def test_ats_detect_personio():
    assert detect_ats("https://acme.jobs.personio.de/") == ("personio", "acme")

def test_dispatch_routes_workable(tmp_path, monkeypatch):
    import scrape.careers_client as cc
    called = {}
    monkeypatch.setattr(cc, "scrape_workable", lambda slug: called.setdefault("slug", slug) or [])
    client = CareersClient(cache_dir=tmp_path, cache_enabled=False, discovery_enabled=False)
    company = CompanyEntry("Acme", "workable", "acme", [])
    client._scrape_one(company, "engineer")
    assert called["slug"] == "acme"
