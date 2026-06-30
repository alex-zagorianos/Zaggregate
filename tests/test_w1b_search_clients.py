"""Wave 1b - SerpApi pagination guard, Careerjet deterministic id, JSON-LD url-less."""
from search.serpapi_client import SerpApiClient
from search.careerjet_client import CareerjetClient
from scrape.jsonld_scraper import extract_jobs


def test_serpapi_page2_short_circuits():
    c = SerpApiClient(api_key="test-key", cache_enabled=False)
    assert c.search("controls engineer", page=2) == {"jobs_results": []}


def test_careerjet_job_id_is_deterministic():
    raw = {"jobs": [{"url": "https://x.co/1", "title": "Controls Engineer",
                     "company": "Acme", "date": "2026-06-30", "description": ""}]}
    c = CareerjetClient()
    a = c.parse_results(raw, "k")[0].job_id
    b = c.parse_results(raw, "k")[0].job_id
    assert a == b and a.startswith("careerjet_")


def test_jsonld_urlless_posting_kept_with_synth_url():
    html = ('<script type="application/ld+json">'
            '{"@type":"JobPosting","title":"Controls Engineer",'
            '"hiringOrganization":{"name":"Acme"}}</script>')
    jobs = extract_jobs(html, "https://acme.com/careers")
    assert jobs and jobs[0].url.startswith("https://acme.com/careers")
