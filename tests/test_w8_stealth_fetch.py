"""Wave 8 - Scrapling stealth/JS fetch fallback seam.

All tests mock scrapling; no real browser or network calls are made.
"""
from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Ensure project root is importable.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import config as cfg
import scrape.direct_scraper as ds
import scrape.stealth_fetch as sf
from scrape.company_registry import CompanyEntry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _company(slug="https://careers.example.com"):
    return CompanyEntry(name="Example Corp", ats_type="direct", slug=slug)


def _allow_stealth_escalation(monkeypatch):
    """Stub out the robots.txt check so fallback-mechanics tests never make a
    real network call and aren't testing robots.txt behavior (that's covered
    separately below + in tests/discover/test_career_link.py)."""
    monkeypatch.setattr(ds, "_stealth_escalation_allowed", lambda company: True)


class _FakeResp:
    """Minimal requests.Response stand-in."""
    def __init__(self, text="", status_code=200):
        self.text = text
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")


# Long enough (> 2000 chars) and has <a links so _looks_js_shell returns False.
_GOOD_HTML = (
    "<html><body>"
    + "<a href='/jobs/123'>Controls Engineer</a>" * 60
    + "</body></html>"
)

_JS_SHELL = "<html><body><div id='root'></div></body></html>"


# ---------------------------------------------------------------------------
# _fetch_html tests
# ---------------------------------------------------------------------------

def test_fallback_html_returned_when_requests_raises(monkeypatch, tmp_path):
    """requests.get raises; fallback yields HTML -> return it, no mark_failed."""
    def _boom(*a, **k):
        raise Exception("connection refused")

    monkeypatch.setattr(ds.requests, "get", _boom)
    monkeypatch.setattr(cfg, "SCRAPLING_FALLBACK", True)
    monkeypatch.setattr(sf, "available", lambda: True)
    monkeypatch.setattr(sf, "fetch_html", lambda url, company=None: _GOOD_HTML)
    _allow_stealth_escalation(monkeypatch)

    # Patch mark_failed in the direct_scraper namespace (imported at top level).
    called = []
    monkeypatch.setattr(ds, "mark_failed", lambda p: called.append(p))

    result = ds._fetch_html(_company(), tmp_path, cache_enabled=False)

    assert result == _GOOD_HTML
    assert called == [], "mark_failed must NOT be called when the fallback succeeds"


def test_mark_failed_when_both_requests_and_fallback_fail(monkeypatch, tmp_path):
    """requests raises; fallback also returns None -> mark_failed + return None."""
    def _boom(*a, **k):
        raise Exception("timeout")

    monkeypatch.setattr(ds.requests, "get", _boom)
    monkeypatch.setattr(cfg, "SCRAPLING_FALLBACK", True)
    monkeypatch.setattr(sf, "available", lambda: True)
    monkeypatch.setattr(sf, "fetch_html", lambda url, company=None: None)
    _allow_stealth_escalation(monkeypatch)

    called = []
    monkeypatch.setattr(ds, "mark_failed", lambda p: called.append(p))

    result = ds._fetch_html(_company(), tmp_path, cache_enabled=True)

    assert result is None
    assert len(called) == 1, "mark_failed must be called when both paths fail"


def test_fallback_not_called_on_good_requests_response(monkeypatch, tmp_path):
    """Good requests HTML -> fallback is never invoked."""
    monkeypatch.setattr(
        ds.requests, "get",
        lambda *a, **k: _FakeResp(text=_GOOD_HTML)
    )
    monkeypatch.setattr(cfg, "SCRAPLING_FALLBACK", True)
    monkeypatch.setattr(sf, "available", lambda: True)

    fallback_calls = []
    monkeypatch.setattr(sf, "fetch_html", lambda url: fallback_calls.append(url) or _GOOD_HTML)

    result = ds._fetch_html(_company(), tmp_path, cache_enabled=False)

    assert result == _GOOD_HTML
    assert fallback_calls == [], "stealth fetch must NOT be called when requests returns good HTML"


def test_fallback_tried_on_js_shell_200(monkeypatch, tmp_path):
    """requests returns 200 with JS shell -> fallback is tried; rendered HTML returned."""
    monkeypatch.setattr(
        ds.requests, "get",
        lambda *a, **k: _FakeResp(text=_JS_SHELL)
    )
    monkeypatch.setattr(cfg, "SCRAPLING_FALLBACK", True)
    monkeypatch.setattr(sf, "available", lambda: True)
    monkeypatch.setattr(sf, "fetch_html", lambda url, company=None: _GOOD_HTML)
    _allow_stealth_escalation(monkeypatch)

    result = ds._fetch_html(_company(), tmp_path, cache_enabled=False)

    assert result == _GOOD_HTML


def test_fallback_disabled_by_config(monkeypatch, tmp_path):
    """SCRAPLING_FALLBACK=False -> fallback never called even on requests failure."""
    def _boom(*a, **k):
        raise Exception("blocked")

    monkeypatch.setattr(ds.requests, "get", _boom)
    monkeypatch.setattr(cfg, "SCRAPLING_FALLBACK", False)
    monkeypatch.setattr(sf, "available", lambda: True)

    fallback_calls = []
    monkeypatch.setattr(sf, "fetch_html", lambda url: fallback_calls.append(url) or _GOOD_HTML)

    called = []
    monkeypatch.setattr(ds, "mark_failed", lambda p: called.append(p))

    result = ds._fetch_html(_company(), tmp_path, cache_enabled=True)

    assert result is None
    assert fallback_calls == [], "stealth fetch must NOT be called when config disables it"
    assert len(called) == 1


# ---------------------------------------------------------------------------
# robots.txt gate before stealth escalation (research-2026-07-01-reach-stealth-legal.md #3.4)
# ---------------------------------------------------------------------------

def test_stealth_escalation_skipped_when_robots_disallows_on_requests_exception(monkeypatch, tmp_path):
    """requests raises AND robots.txt disallows this path -> stealth fetch is
    never invoked; treated the same as a normal double-failure (mark_failed)."""
    def _boom(*a, **k):
        raise Exception("blocked")

    monkeypatch.setattr(ds.requests, "get", _boom)
    monkeypatch.setattr(cfg, "SCRAPLING_FALLBACK", True)
    monkeypatch.setattr(sf, "available", lambda: True)
    monkeypatch.setattr(ds, "_stealth_escalation_allowed", lambda company: False)

    fallback_calls = []
    monkeypatch.setattr(sf, "fetch_html", lambda url, company=None: fallback_calls.append(url) or _GOOD_HTML)

    called = []
    monkeypatch.setattr(ds, "mark_failed", lambda p: called.append(p))

    result = ds._fetch_html(_company(), tmp_path, cache_enabled=True)

    assert result is None
    assert fallback_calls == [], "stealth fetch must NOT be called when robots.txt disallows"
    assert len(called) == 1


def test_stealth_escalation_skipped_when_robots_disallows_on_js_shell(monkeypatch, tmp_path):
    """Good 200 response but a JS shell AND robots.txt disallows -> stealth is
    skipped, the (shell) HTML from requests is still returned as-is."""
    monkeypatch.setattr(ds.requests, "get", lambda *a, **k: _FakeResp(text=_JS_SHELL))
    monkeypatch.setattr(cfg, "SCRAPLING_FALLBACK", True)
    monkeypatch.setattr(sf, "available", lambda: True)
    monkeypatch.setattr(ds, "_stealth_escalation_allowed", lambda company: False)

    fallback_calls = []
    monkeypatch.setattr(sf, "fetch_html", lambda url, company=None: fallback_calls.append(url) or _GOOD_HTML)

    result = ds._fetch_html(_company(), tmp_path, cache_enabled=False)

    assert result == _JS_SHELL
    assert fallback_calls == []


def test_stealth_escalation_allowed_calls_career_link_is_disallowed(monkeypatch):
    """_stealth_escalation_allowed wires to discover.career_link.is_disallowed,
    passing the company's slug, and returns its (negated) verdict."""
    import discover.career_link as career_link

    seen = []

    def fake_is_disallowed(url, user_agent="*"):
        seen.append(url)
        return True  # disallowed

    monkeypatch.setattr(career_link, "is_disallowed", fake_is_disallowed)
    company = _company(slug="https://careers.example.com/jobs")

    assert ds._stealth_escalation_allowed(company) is False
    assert seen == ["https://careers.example.com/jobs"]

    monkeypatch.setattr(career_link, "is_disallowed", lambda url, user_agent="*": False)
    assert ds._stealth_escalation_allowed(company) is True


def test_fetch_html_called_with_company_for_allowlist_propagation(monkeypatch, tmp_path):
    """_fetch_html passes `company=` through to stealth_fetch.fetch_html so the
    allowlist guard can verify the URL belongs to the CompanyEntry that
    triggered it (not just the bare URL string)."""
    def _boom(*a, **k):
        raise Exception("blocked")

    monkeypatch.setattr(ds.requests, "get", _boom)
    monkeypatch.setattr(cfg, "SCRAPLING_FALLBACK", True)
    monkeypatch.setattr(sf, "available", lambda: True)
    _allow_stealth_escalation(monkeypatch)

    received = {}

    def fake_fetch_html(url, company=None):
        received["url"] = url
        received["company"] = company
        return _GOOD_HTML

    monkeypatch.setattr(sf, "fetch_html", fake_fetch_html)

    company = _company()
    ds._fetch_html(company, tmp_path, cache_enabled=False)

    assert received["company"] is company
    assert received["url"] == company.slug


# ---------------------------------------------------------------------------
# stealth_fetch module tests
# ---------------------------------------------------------------------------

def test_stealth_fetch_returns_none_when_scrapling_not_installed(monkeypatch):
    """When scrapling is not importable, fetch_html returns None gracefully."""
    # Remove any real scrapling from sys.modules and block the import.
    monkeypatch.delitem(sys.modules, "scrapling", raising=False)
    monkeypatch.delitem(sys.modules, "scrapling.fetchers", raising=False)

    # Make the import fail by injecting a broken finder.
    real_import = __builtins__.__import__ if hasattr(__builtins__, "__import__") else None

    import builtins
    original_import = builtins.__import__

    def _blocking_import(name, *args, **kwargs):
        if name.startswith("scrapling"):
            raise ModuleNotFoundError(f"No module named '{name}'")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _blocking_import)

    result = sf.fetch_html("https://example.com/careers")
    assert result is None


def test_stealth_fetch_available_false_when_scrapling_missing(monkeypatch):
    """available() returns False when scrapling cannot be imported."""
    monkeypatch.delitem(sys.modules, "scrapling", raising=False)

    import builtins
    original_import = builtins.__import__

    def _blocking_import(name, *args, **kwargs):
        if name.startswith("scrapling"):
            raise ModuleNotFoundError(f"No module named '{name}'")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _blocking_import)

    assert sf.available() is False


def test_stealth_fetch_available_true_when_scrapling_present(monkeypatch):
    """available() returns True when scrapling is present (faked in sys.modules)."""
    fake_scrapling = types.ModuleType("scrapling")
    monkeypatch.setitem(sys.modules, "scrapling", fake_scrapling)

    assert sf.available() is True


def test_stealth_fetch_fetch_html_returns_none_on_empty_url():
    """fetch_html('') short-circuits immediately without touching scrapling."""
    assert sf.fetch_html("") is None


def _fake_scrapling(monkeypatch, html=_GOOD_HTML, status=200):
    """Install a fake scrapling.fetchers.StealthyFetcher in sys.modules and
    return the MagicMock fetcher so callers can assert on it."""
    fake_page = MagicMock()
    fake_page.html_content = html
    fake_page.status = status

    fake_fetcher = MagicMock()
    fake_fetcher.fetch.return_value = fake_page

    fake_fetchers_mod = types.ModuleType("scrapling.fetchers")
    fake_fetchers_mod.StealthyFetcher = fake_fetcher

    fake_scrapling = types.ModuleType("scrapling")

    monkeypatch.setitem(sys.modules, "scrapling", fake_scrapling)
    monkeypatch.setitem(sys.modules, "scrapling.fetchers", fake_fetchers_mod)
    return fake_fetcher


def test_stealth_fetch_fetch_html_uses_stealthy_fetcher(monkeypatch):
    """fetch_html delegates to StealthyFetcher.fetch and extracts html_content,
    for a URL whose host matches the CompanyEntry that triggered the fetch."""
    monkeypatch.setattr(sf, "_host_limiters", {})
    fake_fetcher = _fake_scrapling(monkeypatch)

    result = sf.fetch_html("https://careers.example.com", company=_company())

    assert result == _GOOD_HTML
    fake_fetcher.fetch.assert_called_once_with(
        "https://careers.example.com", headless=True, network_idle=True
    )


# ---------------------------------------------------------------------------
# fetch_html — same-host/registry-domain allowlist guard
# ---------------------------------------------------------------------------

def test_fetch_html_rejects_url_not_in_registry_when_no_company(monkeypatch):
    """No `company` supplied and the URL's host isn't in the curated registry
    -> reject (None), StealthyFetcher never touched. Closes the latent misuse
    path where a future caller could route an arbitrary/aggregator URL through
    the stealth browser."""
    monkeypatch.setattr(sf, "_host_limiters", {})
    monkeypatch.setattr(sf, "_registry_hosts", lambda: {"careers.other-co.example"})
    fake_fetcher = _fake_scrapling(monkeypatch)

    result = sf.fetch_html("https://www.linkedin.com/jobs/view/123")

    assert result is None
    fake_fetcher.fetch.assert_not_called()


def test_fetch_html_allows_url_whose_host_is_in_registry(monkeypatch):
    """No `company` supplied, but the URL's host IS in the curated registry
    (e.g. a call from the JSON-LD scraper, which doesn't carry a CompanyEntry)
    -> allowed."""
    monkeypatch.setattr(sf, "_host_limiters", {})
    monkeypatch.setattr(sf, "_registry_hosts", lambda: {"careers.example.com"})
    fake_fetcher = _fake_scrapling(monkeypatch)

    result = sf.fetch_html("https://careers.example.com/openings")

    assert result == _GOOD_HTML
    fake_fetcher.fetch.assert_called_once()


def test_fetch_html_rejects_mismatched_company_host(monkeypatch):
    """`company` supplied but its slug's host differs from `url`'s host
    -> reject. A future caller can't launder an arbitrary URL through a
    CompanyEntry that doesn't actually own it."""
    monkeypatch.setattr(sf, "_host_limiters", {})
    fake_fetcher = _fake_scrapling(monkeypatch)
    other_company = _company(slug="https://careers.other-co.example")

    result = sf.fetch_html("https://www.indeed.com/jobs?q=welder", company=other_company)

    assert result is None
    fake_fetcher.fetch.assert_not_called()


def test_fetch_html_company_slug_host_ignores_registry(monkeypatch):
    """When `company` is supplied and its host matches, the registry lookup is
    irrelevant (still allowed even if _registry_hosts is empty) -- the direct
    per-call company check is sufficient on its own."""
    monkeypatch.setattr(sf, "_host_limiters", {})
    monkeypatch.setattr(sf, "_registry_hosts", lambda: set())
    fake_fetcher = _fake_scrapling(monkeypatch)

    result = sf.fetch_html("https://careers.example.com", company=_company())

    assert result == _GOOD_HTML
    fake_fetcher.fetch.assert_called_once()


def test_registry_hosts_reads_get_registry(monkeypatch):
    """_registry_hosts() derives hostnames from scrape.company_registry.get_registry()
    (URL-shaped slugs only) and fails soft (empty set) on any error."""
    from scrape.company_registry import CompanyEntry as CE

    fake_entries = [
        CE("Acme", "direct", "https://careers.acme.example/jobs"),
        CE("Beta", "greenhouse", "beta"),  # not a URL -> no host contributed
    ]
    monkeypatch.setattr("scrape.company_registry.get_registry", lambda: fake_entries)

    hosts = sf._registry_hosts()
    assert hosts == {"careers.acme.example"}

    monkeypatch.setattr("scrape.company_registry.get_registry",
                         lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    assert sf._registry_hosts() == set()


# ---------------------------------------------------------------------------
# fetch_html — per-domain rate limiter
# ---------------------------------------------------------------------------

def test_fetch_html_acquires_per_host_rate_limiter(monkeypatch):
    """Every stealth escalation goes through a per-host RateLimiter.acquire()
    before StealthyFetcher.fetch is called -- confirmed by checking a limiter
    instance was created and used for this host."""
    monkeypatch.setattr(sf, "_host_limiters", {})
    fake_fetcher = _fake_scrapling(monkeypatch)

    sf.fetch_html("https://careers.example.com", company=_company())

    assert "careers.example.com" in sf._host_limiters
    limiter = sf._host_limiters["careers.example.com"]
    assert len(limiter._stamps) == 1, "acquire() must record one timestamp for this fetch"


def test_fetch_html_reuses_same_limiter_across_calls_to_same_host(monkeypatch):
    monkeypatch.setattr(sf, "_host_limiters", {})
    _fake_scrapling(monkeypatch)

    sf.fetch_html("https://careers.example.com/a", company=_company())
    sf.fetch_html("https://careers.example.com/b", company=_company())

    assert len(sf._host_limiters) == 1
    assert len(sf._host_limiters["careers.example.com"]._stamps) == 2


def test_fetch_html_does_not_rate_limit_when_url_is_rejected(monkeypatch):
    """A rejected (disallowed-host) URL must never touch the rate limiter or
    the browser -- the allowlist guard runs first."""
    monkeypatch.setattr(sf, "_host_limiters", {})
    monkeypatch.setattr(sf, "_registry_hosts", lambda: set())
    fake_fetcher = _fake_scrapling(monkeypatch)

    result = sf.fetch_html("https://www.linkedin.com/jobs/view/123")

    assert result is None
    assert sf._host_limiters == {}
    fake_fetcher.fetch.assert_not_called()
