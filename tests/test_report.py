from search.report_html import generate_html_report, safe_url
from models import JobResult


def test_safe_url_filter():
    assert safe_url("https://x.com/1") == "https://x.com/1"
    assert safe_url("javascript:alert(1)") == "#"
    assert safe_url("data:text/html,x") == "#"
    assert safe_url("") == "#"


def _job(url):
    return JobResult(
        title="Engineer", company="Acme", location="Cincinnati, OH",
        salary_min=None, salary_max=None, description="", url=url,
        source_keyword="controls engineer", created="2026-06-01",
        job_id="x", source_api="adzuna",
    )


def test_report_neutralizes_javascript_url(tmp_path):
    out = tmp_path / "r.html"
    generate_html_report(
        [_job("javascript:fetch('http://evil')")], out,
        {"date": "2026-06-01", "location": "Cincinnati", "keywords": ["x"],
         "salary_min": None, "sources": ["adzuna"]},
    )
    html = out.read_text(encoding="utf-8")
    assert "javascript:fetch" not in html
    assert 'href="#"' in html


def test_report_preserves_http_url(tmp_path):
    out = tmp_path / "r.html"
    generate_html_report(
        [_job("https://jobs.example.com/123")], out,
        {"date": "2026-06-01", "location": "Cincinnati", "keywords": ["x"],
         "salary_min": None, "sources": ["adzuna"]},
    )
    assert "https://jobs.example.com/123" in out.read_text(encoding="utf-8")
