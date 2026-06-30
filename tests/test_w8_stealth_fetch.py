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
    monkeypatch.setattr(sf, "fetch_html", lambda url: _GOOD_HTML)

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
    monkeypatch.setattr(sf, "fetch_html", lambda url: None)

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
    monkeypatch.setattr(sf, "fetch_html", lambda url: _GOOD_HTML)

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


def test_stealth_fetch_fetch_html_uses_stealthy_fetcher(monkeypatch):
    """fetch_html delegates to StealthyFetcher.fetch and extracts html_content."""
    fake_page = MagicMock()
    fake_page.html_content = _GOOD_HTML
    fake_page.status = 200

    fake_fetcher = MagicMock()
    fake_fetcher.fetch.return_value = fake_page

    fake_fetchers_mod = types.ModuleType("scrapling.fetchers")
    fake_fetchers_mod.StealthyFetcher = fake_fetcher

    fake_scrapling = types.ModuleType("scrapling")

    monkeypatch.setitem(sys.modules, "scrapling", fake_scrapling)
    monkeypatch.setitem(sys.modules, "scrapling.fetchers", fake_fetchers_mod)

    result = sf.fetch_html("https://careers.example.com")

    assert result == _GOOD_HTML
    fake_fetcher.fetch.assert_called_once_with(
        "https://careers.example.com", headless=True, network_idle=True
    )
