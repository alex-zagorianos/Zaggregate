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


# ---------------------------------------------------------------------------
# is_disallowed — robots.txt Disallow check before stealth-escalating
# ---------------------------------------------------------------------------

def _robots(rules: str) -> str:
    return rules


def test_is_disallowed_true_for_explicit_disallow(monkeypatch):
    C._ROBOTS_CACHE.clear()
    robots_txt = "User-agent: *\nDisallow: /careers/blocked\n"
    monkeypatch.setattr(C, "_get", lambda url: robots_txt if url.endswith("robots.txt") else None)
    assert C.is_disallowed("https://example.com/careers/blocked") is True


def test_is_disallowed_false_when_path_allowed(monkeypatch):
    C._ROBOTS_CACHE.clear()
    robots_txt = "User-agent: *\nDisallow: /admin\n"
    monkeypatch.setattr(C, "_get", lambda url: robots_txt if url.endswith("robots.txt") else None)
    assert C.is_disallowed("https://example.com/careers/open-role") is False


def test_is_disallowed_fails_open_when_robots_unreachable(monkeypatch):
    """No binding legal force (Ziff Davis v. OpenAI, 2025) — a fetch hiccup must
    never block a working career page. Fail-open, not fail-closed."""
    C._ROBOTS_CACHE.clear()
    monkeypatch.setattr(C, "_get", lambda url: None)
    assert C.is_disallowed("https://example.com/careers/open-role") is False


def test_is_disallowed_fails_open_on_malformed_url(monkeypatch):
    C._ROBOTS_CACHE.clear()
    assert C.is_disallowed("not-a-url") is False
    assert C.is_disallowed("") is False


def test_is_disallowed_caches_robots_parse(monkeypatch):
    """The robots.txt parse is cached per-origin — a second lookup on the same
    origin must not re-fetch."""
    C._ROBOTS_CACHE.clear()
    calls = []

    def fake_get(url):
        calls.append(url)
        return "User-agent: *\nDisallow: /blocked\n" if url.endswith("robots.txt") else None

    monkeypatch.setattr(C, "_get", fake_get)
    C.is_disallowed("https://example.com/blocked")
    C.is_disallowed("https://example.com/blocked/sub")
    robots_fetches = [u for u in calls if u.endswith("robots.txt")]
    assert len(robots_fetches) == 1, "robots.txt must be fetched once per origin, not per call"
