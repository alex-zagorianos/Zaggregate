"""Stealth/JS fetch fallback via Scrapling (lazy, optional).

Backstop for `scrape/direct_scraper._fetch_html`: when plain `requests` is
blocked (403/anti-bot) or returns a JS-only shell, render the page locally with
Scrapling. Scrapling + its browser binaries are heavy and optional, so the import
is lazy and a missing package degrades to None (the caller then gives up as
before). No network/browser work happens unless this is actually called.

Stealth engine relied on: Scrapling's `StealthyFetcher` (see requirements.txt —
pinned version). As of Scrapling >=0.3.13 its default engine is **Patchright**
(a CDP-level-patched Playwright/Chromium fork); **Camoufox** (a fingerprint-
spoofing Firefox fork) remains available as an opt-in alternate engine. Both are
lower-overhead than a plain Chromium+playwright-stealth stack but still cost a
one-time ~150-300MB browser download (`install()` below) and ~250-900MB RAM per
page while rendering — hence lazy import + opt-in (`config.SCRAPLING_FALLBACK`).

Legal-boundary guards (research-2026-07-01-reach-stealth-legal.md #3.4):
1. Same-host / registry-domain ALLOWLIST — `fetch_html()` only ever renders a
   URL whose host belongs to a company already in the curated scrape registry
   (`scrape/company_registry.py`), never an arbitrary URL. Never LinkedIn/Indeed
   or any authenticated surface — those go through the user-gated browser
   extension instead.
2. Per-domain RATE LIMIT — a small per-host cooldown before every stealth
   escalation so a single low-volume, non-abusive fetch pattern holds in
   practice, not just as policy (mirrors `search.http_util.RateLimiter`, used
   by the API clients but previously absent from this path entirely).
"""
from __future__ import annotations

import threading
from urllib.parse import urlsplit

from search.http_util import RateLimiter

# Per-host RateLimiter instances (module-level, process-lifetime). Kept small
# and dependency-light — reuses the same limiter class the API clients use.
_host_limiters: dict[str, RateLimiter] = {}
_host_limiters_lock = threading.Lock()


def available() -> bool:
    """True if the scrapling package is importable."""
    try:
        import scrapling  # noqa: F401
        return True
    except Exception:
        return False


def browsers_ready() -> bool:
    """Best-effort: True when Scrapling AND a Playwright Chromium are installed, so
    stealth fetching will actually work (not just import). Used by the GUI to show
    'Enable stealth fetching' vs 'Stealth fetching ready'."""
    if not available():
        return False
    try:
        import os
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            path = p.chromium.executable_path
        return bool(path and os.path.exists(path))
    except Exception:
        return False


def install(timeout: int = 900) -> "tuple[bool, str]":
    """One-time download of the stealth/JS browser (Chromium, ~300MB) so the
    fallback can run. Returns (ok, message). Works from source (python) and
    best-effort in a frozen build via the bundled Playwright driver; on failure
    the message carries the manual command for the user."""
    import os
    import subprocess
    import sys
    if not available():
        return False, ("Scrapling isn't installed. From source: "
                       "pip install \"scrapling[fetchers]\".")
    attempts = []  # (argv, env)
    # Frozen-safe path: drive the bundled Playwright node CLI directly.
    try:
        from playwright._impl._driver import compute_driver_executable, get_driver_env
        drv = compute_driver_executable()
        argv = (list(drv) if isinstance(drv, (list, tuple)) else [drv]) + ["install", "chromium"]
        attempts.append((argv, {**os.environ, **get_driver_env()}))
    except Exception:
        pass
    # Dev fallback: the module CLI (sys.executable is python when not frozen).
    if not getattr(sys, "frozen", False):
        attempts.append(([sys.executable, "-m", "playwright", "install", "chromium"], None))
    last = ""
    for argv, env in attempts:
        try:
            r = subprocess.run(argv, capture_output=True, text=True,
                               timeout=timeout, env=env)
            if r.returncode == 0:
                return True, "Stealth fetching is ready."
            last = (r.stderr or r.stdout or "").strip()[-300:]
        except Exception as e:
            last = f"{type(e).__name__}: {e}"
    return False, ("Couldn't install the stealth browser automatically. "
                   f"Run this once in a terminal:  scrapling install\n{last}".strip())


def _registry_hosts() -> set[str]:
    """Hostnames of every company in the curated scrape registry (hardcoded
    industries + companies.json), lowercased. Only entries whose slug is a full
    URL (ats_type='direct', or any future type) contribute a host — ATS-slug
    entries (greenhouse/lever/ashby/smartrecruiters) don't route through this
    fetcher at all. Best-effort: any per-entry parse error is skipped, never
    raised (registry data may come from user-editable companies.json)."""
    try:
        from scrape.company_registry import get_registry
        entries = get_registry()
    except Exception:
        return set()
    hosts: set[str] = set()
    for entry in entries:
        try:
            host = urlsplit(entry.slug).hostname
        except Exception:
            host = None
        if host:
            hosts.add(host.lower())
    return hosts


def _host_allowed(url: str, company=None) -> "str | None":
    """Same-host/registry-domain allowlist guard. Returns the lowercased host if
    `url` is allowed to be stealth-fetched, else None.

    - When `company` (a CompanyEntry) is supplied, `url`'s host must match the
      host of `company.slug` exactly — i.e. this fetch must be for the SAME
      company that triggered it, not some other URL routed through by mistake.
    - When no `company` is supplied, `url`'s host must belong to the curated
      scrape registry (a company we're already scraping) — never an arbitrary
      URL (e.g. an aggregator page, LinkedIn, Indeed).
    """
    try:
        host = urlsplit(url).hostname
    except Exception:
        host = None
    if not host:
        return None
    host = host.lower()
    if company is not None:
        try:
            company_host = urlsplit(getattr(company, "slug", "") or "").hostname
        except Exception:
            company_host = None
        if company_host and host == company_host.lower():
            return host
        return None
    if host in _registry_hosts():
        return host
    return None


def _limiter_for(host: str) -> RateLimiter:
    with _host_limiters_lock:
        limiter = _host_limiters.get(host)
        if limiter is None:
            import config
            limiter = RateLimiter(config.STEALTH_FETCH_RATE_LIMIT, quiet=True)
            _host_limiters[host] = limiter
        return limiter


def fetch_html(url: str, *, company=None) -> "str | None":
    """Return rendered HTML for `url` using Scrapling, or None if Scrapling is
    absent, the fetch fails, or `url` fails the same-host/registry-domain
    allowlist guard (see module docstring). Rate-limited per host before every
    browser escalation. Tries the lightweight Fetcher first, then escalates
    to the stealth browser fetcher on a block. Confirm exact method/param names
    against the installed scrapling version; guard everything so an API shift
    degrades to None rather than raising."""
    if not url:
        return None
    host = _host_allowed(url, company)
    if host is None:
        return None
    try:
        from scrapling.fetchers import StealthyFetcher
    except Exception:
        return None
    _limiter_for(host).acquire()
    try:
        page = StealthyFetcher.fetch(url, headless=True, network_idle=True)
        html = getattr(page, "html_content", None) or getattr(page, "body", None)
        status = getattr(page, "status", 200)
        # Re-vet the FINAL navigated URL: a registry company's page can 301/302/JS-
        # redirect to an un-vetted host, and the pre-navigation allowlist check
        # wouldn't have seen it. If the browser ended up somewhere not allowed (or
        # robots-disallowed), drop the HTML rather than scrape an unapproved host.
        final_url = getattr(page, "url", None)
        if not isinstance(final_url, str) or not final_url:
            final_url = url          # no usable final URL -> nothing to re-vet
        if final_url != url:
            if _host_allowed(final_url, company) is None:
                return None
            try:
                from discover.career_link import is_disallowed
                if is_disallowed(final_url):
                    return None
            except Exception:
                pass  # robots check is fail-open
        if html and (status is None or status == 200):
            return html
    except Exception:
        return None
    return None
