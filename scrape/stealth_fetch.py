"""Stealth/JS fetch fallback via Scrapling (lazy, optional).

Backstop for `scrape/direct_scraper._fetch_html`: when plain `requests` is
blocked (403/anti-bot) or returns a JS-only shell, render the page locally with
Scrapling. Scrapling + its browser binaries are heavy and optional, so the import
is lazy and a missing package degrades to None (the caller then gives up as
before). No network/browser work happens unless this is actually called.
"""
from __future__ import annotations


def available() -> bool:
    """True if the scrapling package is importable."""
    try:
        import scrapling  # noqa: F401
        return True
    except Exception:
        return False


def fetch_html(url: str) -> "str | None":
    """Return rendered HTML for `url` using Scrapling, or None if Scrapling is
    absent or the fetch fails. Tries the lightweight Fetcher first, then escalates
    to the stealth browser fetcher on a block. Confirm exact method/param names
    against the installed scrapling version; guard everything so an API shift
    degrades to None rather than raising."""
    if not url:
        return None
    try:
        from scrapling.fetchers import StealthyFetcher
    except Exception:
        return None
    try:
        page = StealthyFetcher.fetch(url, headless=True, network_idle=True)
        html = getattr(page, "html_content", None) or getattr(page, "body", None)
        status = getattr(page, "status", 200)
        if html and (status is None or status == 200):
            return html
    except Exception:
        return None
    return None
