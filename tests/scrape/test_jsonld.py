from pathlib import Path
from scrape.jsonld_scraper import extract_jobs

FX = Path(__file__).resolve().parents[1] / "fixtures" / "ws2"

def _html():
    return (FX / "jsonld_page.html").read_text(encoding="utf-8")

def test_extracts_jobposting():
    jobs = extract_jobs(_html(), "https://gamma.example")
    assert len(jobs) == 1
    j = jobs[0]
    assert j.title == "Mechatronics Engineer"
    assert j.company == "Gamma Industries"
    assert "Cincinnati" in j.location and "OH" in j.location
    assert j.salary_min == 95000 and j.salary_max == 130000
    assert j.created == "2026-06-07"
    assert "mechatronic" in j.description.lower()  # HTML stripped

def test_no_jsonld_returns_empty():
    assert extract_jobs("<html><body>nothing</body></html>", "https://x") == []

def test_malformed_jsonld_skipped():
    bad = '<script type="application/ld+json">{not json}</script>'
    assert extract_jobs(bad, "https://x") == []
