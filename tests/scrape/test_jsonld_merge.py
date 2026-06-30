"""JSON-LD is wired additively: a direct page that embeds schema.org/JobPosting
data yields those postings too, on top of plain link extraction — never fewer.
Previously jsonld_scraper was implemented but never reachable (orphaned)."""
from scrape.company_registry import CompanyEntry
from scrape.direct_scraper import _extract_jobs, _merge_jsonld
from scrape.jsonld_scraper import extract_jobs, scrape_jsonld

_HTML = """<html><body>
<a href="/jobs/100">Controls Engineer</a>
<script type="application/ld+json">
{"@type":"JobPosting","title":"Controls Engineer II",
 "hiringOrganization":{"name":"Acme"},
 "jobLocation":{"address":{"addressLocality":"Cincinnati","addressRegion":"OH"}},
 "url":"https://acme.com/jobs/200","description":"PLC and controls automation"}
</script></body></html>"""

_COMPANY = CompanyEntry(name="Acme", ats_type="jsonld",
                        slug="https://acme.com/careers", industries=[])


def test_jsonld_merge_is_additive_over_direct():
    direct_only = _extract_jobs(_HTML, _COMPANY, "controls engineer")
    merged = _merge_jsonld(list(direct_only), _HTML, _COMPANY, "controls engineer")
    # Strictly additive: never drops a link-extracted job.
    assert len(merged) >= len(direct_only)
    # The structured JSON-LD posting (distinct URL) is now surfaced.
    assert "https://acme.com/jobs/200" in {j.url for j in merged}


def test_jsonld_merge_dedupes_by_identity():
    # Same job twice (link + LD at the same URL) must not double-count.
    html = ('<a href="https://acme.com/jobs/200">Controls Engineer</a>'
            '<script type="application/ld+json">'
            '{"@type":"JobPosting","title":"Controls Engineer",'
            '"hiringOrganization":{"name":"Acme"},'
            '"url":"https://acme.com/jobs/200","description":"controls"}'
            '</script>')
    direct_only = _extract_jobs(html, _COMPANY, "controls engineer")
    merged = _merge_jsonld(list(direct_only), html, _COMPANY, "controls engineer")
    urls = [j.url for j in merged]
    assert urls.count("https://acme.com/jobs/200") == 1


def test_scrape_jsonld_fills_company_and_filters(monkeypatch):
    import scrape.jsonld_scraper as mod
    monkeypatch.setattr(mod, "_fetch_html", lambda *a, **k: _HTML, raising=False)
    # _fetch_html is imported lazily from direct_scraper inside scrape_jsonld;
    # patch it there instead.
    import scrape.direct_scraper as direct
    monkeypatch.setattr(direct, "_fetch_html", lambda *a, **k: _HTML)
    jobs = scrape_jsonld(_COMPANY, "controls engineer", cache_dir=None, cache_enabled=False)
    assert jobs and all(j.company for j in jobs)
    assert any(j.title.startswith("Controls Engineer") for j in jobs)
    # A non-matching keyword yields nothing (deep title+body filter).
    assert scrape_jsonld(_COMPANY, "phlebotomist", cache_dir=None, cache_enabled=False) == []
