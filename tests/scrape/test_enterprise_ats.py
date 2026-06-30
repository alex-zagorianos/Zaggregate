"""Enterprise ATSes with no JSON API (iCIMS / Taleo / SuccessFactors) are tagged
by detection, routed to the JSON-LD scraper, and probe-counted via JobPosting
structured data so the enumeration verify gate can vet them."""
import scrape.ats_detect as ats_detect
import scrape.careers_client as cc
from scrape.company_registry import CompanyEntry

_JOB_LD = """
<html><head>
<script type="application/ld+json">
{"@type":"JobPosting","title":"Controls Engineer",
 "hiringOrganization":{"name":"Kroger"},
 "jobLocation":{"address":{"addressLocality":"Cincinnati","addressRegion":"OH"}},
 "datePosted":"2026-06-20","description":"PLC and automation work."}
</script></head><body></body></html>
"""


class _Resp:
    ok = True
    def __init__(self, text):
        self.text = text


def test_careers_client_routes_enterprise_to_jsonld(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(cc, "scrape_jsonld",
                        lambda company, kw, cd, ce: calls.append(company.ats_type) or [])
    client = cc.CareersClient(cache_dir=tmp_path, discovery_enabled=False)
    for ats in ("icims", "taleo", "successfactors", "jsonld"):
        client._scrape_one(CompanyEntry("Co", ats, "https://co.example/careers"), "controls")
    assert calls == ["icims", "taleo", "successfactors", "jsonld"]


def test_probe_count_jsonld_counts_jobpostings(monkeypatch):
    import requests
    monkeypatch.setattr(requests, "get", lambda *a, **k: _Resp(_JOB_LD))
    entry = CompanyEntry("Kroger", "icims", "https://careers-kroger.icims.com/jobs")
    assert ats_detect.probe_count(entry) == 1


def test_probe_count_jsonld_zero_when_no_postings(monkeypatch):
    import requests
    monkeypatch.setattr(requests, "get", lambda *a, **k: _Resp("<html>nothing</html>"))
    entry = CompanyEntry("Taleo Co", "taleo", "https://x.taleo.net/careersection")
    assert ats_detect.probe_count(entry) == 0
