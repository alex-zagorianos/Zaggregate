from pathlib import Path
import discover.career_link as C

FX = Path(__file__).resolve().parents[1] / "fixtures" / "ws2"

def _sitemap():
    return (FX / "sitemap.xml").read_text(encoding="utf-8")

def _homepage():
    return (FX / "homepage.html").read_text(encoding="utf-8")

def test_sitemap_job_urls_filters(monkeypatch):
    monkeypatch.setattr(C, "_get", lambda url: _sitemap() if "sitemap" in url else None)
    urls = C.sitemap_job_urls("example.com")
    assert "https://example.com/careers/open-positions" in urls
    assert "https://example.com/jobs/controls-engineer" in urls
    assert all("/blog/" not in u and "/about" not in u for u in urls)

def test_find_career_url_from_anchor(monkeypatch):
    def fake_get(url):
        if url.rstrip("/").endswith("sitemap.xml") or "robots.txt" in url:
            return None
        return _homepage()
    monkeypatch.setattr(C, "_get", fake_get)
    assert C.find_career_url("example.com") == "https://example.com/careers"

def test_find_career_url_none_when_unreachable(monkeypatch):
    monkeypatch.setattr(C, "_get", lambda url: None)
    assert C.find_career_url("example.com") is None
