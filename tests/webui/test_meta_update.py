"""/api/meta/update/* — the Velopack auto-update routes (2026-07-08).

The pre-existing tests in test_meta.py pin the v1.0.2 behaviour and must keep passing
untouched; that is the whole point of the not-managed fallback. These tests pin the
NEW surface:

* update-check reports `managed` and, when managed, sources truth from the SDK (which
  honours the install's channel) rather than GitHub's `releases/latest` tag.
* download/progress/apply exist, are origin-gated where they mutate, and degrade to
  `ok:false, error:"not-managed"` in a dev checkout.
* apply NEVER calls os._exit during a test (it is patched); the route must return the
  response BEFORE the process would exit, which is why the exit is deferred to a thread.
"""
import pytest

import config
import updater
from webui.api import meta as meta_mod


_H = {"Origin": "http://127.0.0.1:5002"}


@pytest.fixture(autouse=True)
def _hermetic(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(config, "USER_DATA_DIR", tmp_path)
    # Never let a test actually kill the pytest process.
    monkeypatch.setattr(meta_mod.os, "_exit", lambda code: None)


# ── not-managed (dev checkout / plain zip): v1.0.2 behaviour, plus a flag ──────

def test_update_check_unmanaged_reports_managed_false(client, monkeypatch):
    monkeypatch.setattr(updater, "is_managed", lambda: False)
    monkeypatch.setattr(meta_mod, "_fetch_latest_tag", lambda: "v9.9.9")
    r = client.post("/api/meta/update-check", headers=_H)
    body = r.get_json()
    assert r.status_code == 200
    assert body["ok"] is True and body["managed"] is False
    assert body["newer"] is True and body["latest"] == "v9.9.9"
    # the link-out URL the v1.0.2 UI opens
    assert body["url"].endswith("/releases")


def test_download_unmanaged_is_benign(client, monkeypatch):
    monkeypatch.setattr(updater, "is_managed", lambda: False)
    r = client.post("/api/meta/update/download", headers=_H)
    assert r.status_code == 200
    assert r.get_json()["failure"] == "not-managed"


def test_apply_unmanaged_is_benign_and_does_not_exit(client, monkeypatch):
    monkeypatch.setattr(updater, "is_managed", lambda: False)
    exits = []
    monkeypatch.setattr(meta_mod.os, "_exit", lambda c: exits.append(c))
    r = client.post("/api/meta/update/apply", headers=_H)
    body = r.get_json()
    assert r.status_code == 200
    assert body["ok"] is False and body["error"] == "not-managed"
    assert exits == []


# ── managed: the SDK is the source of truth ───────────────────────────────────

def test_update_check_managed_uses_the_sdk_not_github(client, monkeypatch):
    """A beta tester must never be told about a stable release their channel can't
    apply, so a managed install must NOT consult GitHub's releases/latest tag."""
    monkeypatch.setattr(updater, "is_managed", lambda: True)
    monkeypatch.setattr(updater, "pending_restart", lambda: False)
    monkeypatch.setattr(updater, "check", lambda: {
        "managed": True, "newer": True, "latest": "1.0.3", "current": "1.0.2"})

    def _boom():
        raise AssertionError("a managed install must not hit the GitHub tag API")

    monkeypatch.setattr(meta_mod, "_fetch_latest_tag", _boom)

    body = client.post("/api/meta/update-check", headers=_H).get_json()
    assert body["managed"] is True
    assert body["newer"] is True and body["latest"] == "1.0.3"


def test_update_check_managed_is_never_cached(client, monkeypatch):
    """The 24h file cache would hide a just-published hotfix from a managed install;
    the SDK call is local and cheap, so it runs every click."""
    monkeypatch.setattr(updater, "is_managed", lambda: True)
    monkeypatch.setattr(updater, "pending_restart", lambda: False)
    calls = []

    def _check():
        calls.append(1)
        return {"managed": True, "newer": False, "latest": None, "current": "1.0.2"}

    monkeypatch.setattr(updater, "check", _check)
    client.post("/api/meta/update-check", headers=_H)
    client.post("/api/meta/update-check", headers=_H)
    assert len(calls) == 2
    assert not (config.CACHE_DIR / "update_check.json").exists()


def test_progress_route_reports_state(client, monkeypatch):
    monkeypatch.setattr(updater, "progress",
                        lambda: {"phase": "downloading", "percent": 42,
                                 "version": "1.0.3", "failure": None})
    body = client.get("/api/meta/update/progress").get_json()
    assert body["ok"] is True and body["phase"] == "downloading"
    assert body["percent"] == 42


def test_apply_managed_returns_then_schedules_exit(client, monkeypatch):
    """The 200 must be produced by the route itself; the process exit is deferred to a
    daemon thread so Velopack's Update.exe sees us exit AFTER the reply flushed."""
    monkeypatch.setattr(updater, "is_managed", lambda: True)
    monkeypatch.setattr(updater, "apply_and_restart",
                        lambda args: {"ok": True, "exiting": True})
    spawned = []
    real_thread = meta_mod.threading.Thread

    class _Spy(real_thread):
        def start(self):
            spawned.append(self.name)   # do NOT run the exit timer

    monkeypatch.setattr(meta_mod.threading, "Thread", _Spy)

    r = client.post("/api/meta/update/apply", headers=_H)
    body = r.get_json()
    assert r.status_code == 200 and body["ok"] is True and body["exiting"] is True
    assert spawned == ["zaggregate-update-exit"]


def test_apply_refusal_does_not_schedule_exit(client, monkeypatch):
    """A --daily run in progress means we answer ok:false and keep running."""
    monkeypatch.setattr(updater, "is_managed", lambda: True)
    monkeypatch.setattr(updater, "apply_and_restart",
                        lambda args: {"ok": False, "exiting": False,
                                      "error": "daily-run-active"})
    spawned = []
    real_thread = meta_mod.threading.Thread

    class _Spy(real_thread):
        def start(self):
            spawned.append(self.name)

    monkeypatch.setattr(meta_mod.threading, "Thread", _Spy)

    body = client.post("/api/meta/update/apply", headers=_H).get_json()
    assert body["ok"] is False and body["error"] == "daily-run-active"
    assert spawned == []


# ── origin gating on the mutating routes ──────────────────────────────────────

@pytest.mark.parametrize("path", ["/api/meta/update/download", "/api/meta/update/apply"])
def test_mutating_update_routes_are_origin_gated(client, path):
    """A cross-site page must not be able to start a download or restart the app."""
    assert client.post(path).status_code == 403
