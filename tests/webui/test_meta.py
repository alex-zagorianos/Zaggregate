"""B1 — /api/meta routes: version, update-check (cached, graceful), feedback.

Covers:
* GET /api/meta/version echoes config.APP_VERSION.
* POST /api/meta/update-check with a monkeypatched urlopen:
    - a NEWER release tag -> newer:true, latest set;
    - the SAME tag -> newer:false;
    - ANY network failure -> latest:null, newer:false, STILL ok:true (never an
      error envelope for a network failure);
    - a conclusive result is cached and the 24h cache is honored (a second call
      does not re-fetch); a failure is NOT cached.
* the update-check route is origin-gated (403 header-less).
* GET /api/meta/feedback-target returns the email + a version-tagged subject.
"""
import json

import pytest

import config
from webui.api import meta as meta_mod


_H = {"Origin": "http://127.0.0.1:5002"}


@pytest.fixture(autouse=True)
def _tmp_cache(tmp_path, monkeypatch):
    """Point the update-check cache dir at a tmp folder so cache tests are
    hermetic and never touch real user data."""
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path / "cache")


def _fake_urlopen(tag, calls=None):
    """A urlopen stand-in that returns a GitHub-shaped releases/latest body with
    the given tag, and (optionally) counts how many times it was called."""
    def _open(req, timeout=None):
        if calls is not None:
            calls.append(getattr(req, "full_url", req))
        body = json.dumps({"tag_name": tag}).encode("utf-8")

        class _Resp:
            def read(self_inner):
                return body

            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, *a):
                return False

        return _Resp()

    return _open


# ── version ───────────────────────────────────────────────────────────────────

def test_version_returns_app_version(client):
    resp = client.get("/api/meta/version")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body == {"ok": True, "version": config.APP_VERSION}


# ── update-check ────────────────────────────────────────────────────────────────

def test_update_check_newer_release(client, monkeypatch):
    monkeypatch.setattr(config, "APP_VERSION", "1.0.0")
    monkeypatch.setattr(meta_mod.urllib.request, "urlopen",
                        _fake_urlopen("v1.2.0"))
    resp = client.post("/api/meta/update-check", headers=_H)
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert body["current"] == "1.0.0"
    assert body["latest"] == "v1.2.0"
    assert body["newer"] is True
    assert config.UPDATE_REPO in body["url"]


def test_update_check_same_version_not_newer(client, monkeypatch):
    monkeypatch.setattr(config, "APP_VERSION", "1.0.0")
    monkeypatch.setattr(meta_mod.urllib.request, "urlopen",
                        _fake_urlopen("v1.0.0"))
    resp = client.post("/api/meta/update-check", headers=_H)
    body = resp.get_json()
    assert body["ok"] is True
    assert body["latest"] == "v1.0.0"
    assert body["newer"] is False


def test_update_check_older_release_not_newer(client, monkeypatch):
    monkeypatch.setattr(config, "APP_VERSION", "2.0.0")
    monkeypatch.setattr(meta_mod.urllib.request, "urlopen",
                        _fake_urlopen("v1.9.9"))
    body = client.post("/api/meta/update-check", headers=_H).get_json()
    assert body["ok"] is True and body["newer"] is False


def test_update_check_network_failure_is_graceful(client, monkeypatch):
    def _boom(req, timeout=None):
        raise OSError("offline")

    monkeypatch.setattr(meta_mod.urllib.request, "urlopen", _boom)
    resp = client.post("/api/meta/update-check", headers=_H)
    # A network failure is NEVER an error envelope — ok:true with latest:null.
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert body["latest"] is None
    assert body["newer"] is False
    assert body["current"] == config.APP_VERSION


def test_update_check_caches_conclusive_result(client, monkeypatch):
    monkeypatch.setattr(config, "APP_VERSION", "1.0.0")
    calls = []
    monkeypatch.setattr(meta_mod.urllib.request, "urlopen",
                        _fake_urlopen("v1.5.0", calls))
    first = client.post("/api/meta/update-check", headers=_H).get_json()
    assert first["latest"] == "v1.5.0"
    assert len(calls) == 1
    # Second call within 24h reads the cache — no second fetch.
    second = client.post("/api/meta/update-check", headers=_H).get_json()
    assert second["latest"] == "v1.5.0"
    assert len(calls) == 1, "cache not honored — urlopen was called again"


def test_update_check_does_not_cache_failure(client, monkeypatch):
    calls = []

    def _boom(req, timeout=None):
        calls.append(1)
        raise OSError("offline")

    monkeypatch.setattr(meta_mod.urllib.request, "urlopen", _boom)
    client.post("/api/meta/update-check", headers=_H)
    # A transient failure is NOT cached — the next click re-probes.
    client.post("/api/meta/update-check", headers=_H)
    assert len(calls) == 2, "a failed check must not be cached"


def test_update_check_is_origin_gated(client):
    # Header-less POST (no Origin/Referer) -> 403 forbidden origin.
    resp = client.post("/api/meta/update-check")
    assert resp.status_code == 403
    assert resp.get_json() == {"ok": False, "error": "forbidden origin"}


# ── feedback-target ─────────────────────────────────────────────────────────────

def test_feedback_target(client, monkeypatch):
    monkeypatch.setattr(config, "APP_VERSION", "1.0.0")
    monkeypatch.setattr(config, "FEEDBACK_EMAIL", "help@example.test")
    resp = client.get("/api/meta/feedback-target")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert body["email"] == "help@example.test"
    assert "1.0.0" in body["subject"]


# ── version-parse helpers (unit) ────────────────────────────────────────────────

@pytest.mark.parametrize("latest,current,expected", [
    ("v1.2.0", "1.0.0", True),
    ("1.2.0", "1.0.0", True),
    ("v1.0.0", "1.0.0", False),
    ("v1.0.0", "1.2.0", False),
    ("v1.2.3-beta", "1.2.2", True),
    ("garbage", "1.0.0", False),   # unparseable never nags
    ("", "1.0.0", False),
])
def test_is_newer(latest, current, expected):
    assert meta_mod._is_newer(latest, current) is expected
