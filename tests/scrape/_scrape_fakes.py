"""Shared fixtures for the ATS-scraper tests.

The careers scrapers now route their HTTP through a shared retry/Retry-After
session (search.http_util.careers_session) guarded by a per-host rate limiter,
instead of a bare requests.get. These helpers let a test replace both with cheap
in-process stand-ins, so the no-cache scraper path stays testable without any
network or real rate-limit sleeps.
"""
from typing import Callable


class FakeResp:
    """Minimal requests.Response stand-in with header + status support."""

    def __init__(self, payload=None, *, status_code=200, text=None,
                 etag=None, last_modified=None):
        self._payload = payload
        self._text = text
        self.status_code = status_code
        self.headers = {}
        if etag:
            self.headers["ETag"] = etag
        if last_modified:
            self.headers["Last-Modified"] = last_modified

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload

    @property
    def text(self):
        return self._text if self._text is not None else ""


class _FakeSession:
    def __init__(self, handler: Callable):
        self._handler = handler

    def get(self, *a, **k):
        return self._handler(*a, **k)

    def post(self, *a, **k):
        return self._handler(*a, **k)


class _NoWaitLimiter:
    def acquire(self):
        return None


def patch_session(monkeypatch, module, handler: Callable):
    """Replace ``module.careers_session`` with a session whose .get/.post call
    ``handler(*a, **k)``, and ``module.careers_host_limiter`` with a no-op
    limiter (no real sleeps)."""
    monkeypatch.setattr(module, "careers_session", lambda: _FakeSession(handler))
    monkeypatch.setattr(module, "careers_host_limiter", lambda host: _NoWaitLimiter())
