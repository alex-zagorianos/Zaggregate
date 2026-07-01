"""HTTP conditional GET (ETag / If-Modified-Since) — free-efficiency feature.

On a same-content daily run, an unchanged ATS board answers 304 Not Modified
instead of re-sending the full JSON payload. These tests are fixture-based
(fake session/requests stand-ins) — no live network.
"""
import os
import time

import requests

from scrape.cache_helpers import conditional_get_json
from scrape.company_registry import CompanyEntry
from scrape.greenhouse_scraper import scrape_greenhouse
from scrape.lever_scraper import scrape_lever


class _FakeResp:
    """Minimal stand-in for a requests.Response, with header support."""

    def __init__(self, payload=None, *, status_code=200, etag=None, last_modified=None):
        self._payload = payload
        self.status_code = status_code
        self.headers = {}
        if etag:
            self.headers["ETag"] = etag
        if last_modified:
            self.headers["Last-Modified"] = last_modified

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


class _FakeSession:
    """Replays a scripted sequence of responses/exceptions, one per .get() call,
    and records the headers it was sent so tests can assert on the conditional
    validators (If-None-Match / If-Modified-Since)."""

    def __init__(self, script):
        self._script = list(script)
        self.calls = []

    def get(self, url, headers=None, timeout=None):
        self.calls.append({"url": url, "headers": dict(headers or {}), "timeout": timeout})
        item = self._script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


# ---------------------------------------------------------------------------
# conditional_get_json — direct unit tests
# ---------------------------------------------------------------------------
def test_http_error_signals_failure_not_stale_body(tmp_path):
    # review r3 F3: a cached board that later 404s (removed/renamed) must return
    # (None, False) so the caller marks it FAILED — never re-serve the stale
    # snapshot as if live (which would resurrect a dead board's jobs forever).
    cache_file = tmp_path / "dead.json"
    ok = _FakeSession([_FakeResp({"jobs": [{"id": 1}]}, status_code=200, etag='W/"x"')])
    body, _ = conditional_get_json("http://x/dead", cache_file, session=ok)
    assert body == {"jobs": [{"id": 1}]}
    gone = _FakeSession([_FakeResp(None, status_code=404)])
    body2, from_cache2 = conditional_get_json("http://x/dead", cache_file, session=gone)
    assert body2 is None and from_cache2 is False


def test_network_error_still_falls_back_to_stale_body(tmp_path):
    # A TRANSIENT network error (no server response) still serves the last-good
    # cached body — that resilience path is preserved by the F3 fix.
    cache_file = tmp_path / "blip.json"
    ok = _FakeSession([_FakeResp({"jobs": [{"id": 1}]}, status_code=200)])
    conditional_get_json("http://x/blip", cache_file, session=ok)
    blip = _FakeSession([requests.ConnectionError("blip")])
    body, from_cache = conditional_get_json("http://x/blip", cache_file, session=blip)
    assert body == {"jobs": [{"id": 1}]} and from_cache is False


def test_first_200_stores_etag_second_304_reuses_cached_body(tmp_path):
    cache_file = tmp_path / "board.json"
    body = {"jobs": [{"id": 1, "title": "Engineer"}]}
    session = _FakeSession([
        _FakeResp(body, status_code=200, etag='W/"abc123"'),
        _FakeResp(status_code=304),
    ])

    data1, from_cache1 = conditional_get_json("https://x/jobs", cache_file, session=session)
    assert data1 == body
    assert from_cache1 is False
    assert "If-None-Match" not in session.calls[0]["headers"]  # nothing cached yet

    data2, from_cache2 = conditional_get_json("https://x/jobs", cache_file, session=session)
    assert data2 == body          # same body, served from cache
    assert from_cache2 is True
    assert session.calls[1]["headers"].get("If-None-Match") == 'W/"abc123"'


def test_no_etag_server_behaves_like_plain_cached_get(tmp_path):
    cache_file = tmp_path / "board.json"
    body = {"jobs": [{"id": 2, "title": "Tech"}]}
    session = _FakeSession([
        _FakeResp(body, status_code=200),   # no ETag/Last-Modified at all
        _FakeResp(body, status_code=200),
    ])

    data1, from_cache1 = conditional_get_json("https://x/jobs", cache_file, session=session)
    assert data1 == body
    assert from_cache1 is False

    # No validator stored -> no conditional header sent next time; still works.
    data2, from_cache2 = conditional_get_json("https://x/jobs", cache_file, session=session)
    assert data2 == body
    assert from_cache2 is False
    assert "If-None-Match" not in session.calls[1]["headers"]
    assert "If-Modified-Since" not in session.calls[1]["headers"]


def test_network_error_falls_back_to_cached_body(tmp_path):
    cache_file = tmp_path / "board.json"
    body = {"jobs": [{"id": 3, "title": "Fitter"}]}
    session = _FakeSession([
        _FakeResp(body, status_code=200, etag='"v1"'),
        requests.ConnectionError("dead host"),
    ])

    data1, _ = conditional_get_json("https://x/jobs", cache_file, session=session)
    assert data1 == body

    data2, from_cache2 = conditional_get_json("https://x/jobs", cache_file, session=session)
    assert data2 == body          # stale-better-than-nothing
    assert from_cache2 is False   # not server-confirmed, just a fallback


def test_network_error_with_no_cache_returns_none_never_raises(tmp_path):
    cache_file = tmp_path / "board.json"
    session = _FakeSession([requests.ConnectionError("dead host")])

    data, from_cache = conditional_get_json("https://x/jobs", cache_file, session=session)
    assert data is None
    assert from_cache is False


def test_last_modified_validator_round_trips(tmp_path):
    cache_file = tmp_path / "board.json"
    body = {"jobs": []}
    session = _FakeSession([
        _FakeResp(body, status_code=200, last_modified="Wed, 01 Jul 2026 00:00:00 GMT"),
        _FakeResp(status_code=304),
    ])
    conditional_get_json("https://x/jobs", cache_file, session=session)
    conditional_get_json("https://x/jobs", cache_file, session=session)
    assert session.calls[1]["headers"].get("If-Modified-Since") == "Wed, 01 Jul 2026 00:00:00 GMT"


# ---------------------------------------------------------------------------
# greenhouse / lever scraper integration — parsed JobResult output must be
# byte-identical whether the payload came fresh (200) or was revalidated
# (304); only the transport changes.
# ---------------------------------------------------------------------------
def _age_cache_file(path, hours):
    old = time.time() - hours * 3600
    os.utime(path, (old, old))


def test_greenhouse_304_reuses_cache_and_matches_200_output(tmp_path, monkeypatch):
    payload = {
        "meta": {"total": 1},
        "jobs": [{
            "id": 42,
            "title": "Controls Engineer",
            "departments": [{"name": "Engineering"}],
            "location": {"name": "Cincinnati, OH"},
            "content": "Design and maintain automation systems.",
            "absolute_url": "https://example.com/42",
            "first_published": "2026-06-01",
        }],
    }
    calls = {"n": 0}

    def fake_get(url, timeout=None, headers=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return _FakeResp(payload, status_code=200, etag='W/"gh-1"')
        return _FakeResp(status_code=304)

    monkeypatch.setattr(requests, "get", fake_get)
    company = CompanyEntry("Acme", "greenhouse", "acme")

    jobs1 = scrape_greenhouse(company, "controls engineer", tmp_path, cache_enabled=True)
    assert len(jobs1) == 1
    assert calls["n"] == 1

    # Force the TTL-fresh fast path to expire (simulate the next daily run) so
    # the second call actually revalidates over the network instead of being
    # absorbed by the in-run cache.
    cache_file = tmp_path / "greenhouse_acme.json"
    _age_cache_file(cache_file, hours=25)

    jobs2 = scrape_greenhouse(company, "controls engineer", tmp_path, cache_enabled=True)
    assert calls["n"] == 2                 # one extra network round-trip (a 304)
    assert jobs2 == jobs1                  # byte-identical parsed output


def test_greenhouse_same_run_second_keyword_no_extra_network_call(tmp_path, monkeypatch):
    payload = {
        "meta": {"total": 1},
        "jobs": [{
            "id": 7,
            "title": "Automation Engineer",
            "departments": [],
            "location": {"name": "Remote"},
            "content": "",
            "absolute_url": "https://example.com/7",
            "first_published": "2026-06-01",
        }],
    }
    calls = {"n": 0}

    def fake_get(url, timeout=None, headers=None):
        calls["n"] += 1
        return _FakeResp(payload, status_code=200, etag='W/"gh-7"')

    monkeypatch.setattr(requests, "get", fake_get)
    company = CompanyEntry("Acme", "greenhouse", "acme")

    scrape_greenhouse(company, "automation engineer", tmp_path, cache_enabled=True)
    scrape_greenhouse(company, "automation engineer", tmp_path, cache_enabled=True)
    assert calls["n"] == 1   # second keyword call within the same run reused the fresh cache


def test_lever_304_reuses_cache_and_matches_200_output(tmp_path, monkeypatch):
    payload = [{
        "id": "a1",
        "text": "Controls Technician",
        "categories": {"team": "Ops", "department": "Engineering", "location": "Remote"},
        "descriptionPlain": "Maintain equipment.",
        "hostedUrl": "https://jobs.lever.co/acme/a1",
        "createdAt": 1750000000000,
    }]
    calls = {"n": 0}

    def fake_get(url, timeout=None, headers=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return _FakeResp(payload, status_code=200, etag='"lv-1"')
        return _FakeResp(status_code=304)

    monkeypatch.setattr(requests, "get", fake_get)
    company = CompanyEntry("Acme", "lever", "acme")

    jobs1 = scrape_lever(company, "controls technician", tmp_path, cache_enabled=True)
    assert len(jobs1) == 1
    assert calls["n"] == 1

    cache_file = tmp_path / "lever_acme.json"
    _age_cache_file(cache_file, hours=25)

    jobs2 = scrape_lever(company, "controls technician", tmp_path, cache_enabled=True)
    assert calls["n"] == 2
    assert jobs2 == jobs1


def test_greenhouse_unreachable_with_no_cache_marks_failed(tmp_path, monkeypatch):
    def boom(url, timeout=None, headers=None):
        raise requests.ConnectionError("dead host")

    monkeypatch.setattr(requests, "get", boom)
    company = CompanyEntry("Dead Co", "greenhouse", "dead")

    assert scrape_greenhouse(company, "controls", tmp_path, cache_enabled=True) == []
    from scrape.cache_helpers import is_failed, read_cache
    cache_file = tmp_path / "greenhouse_dead.json"
    assert is_failed(read_cache(cache_file)) is True
