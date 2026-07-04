"""/api/status + /api/project (list, switch, unknown-slug 400, foreign-origin 403)."""
import pytest

import workspace


_EXT_ORIGIN = "chrome-extension://abcdefghijklmnop"
_FOREIGN_ORIGIN = "https://evil.example.com"


@pytest.fixture
def tmp_projects(tmp_path, monkeypatch):
    """A fresh registry with two projects (the workspace.BASE_DIR fixture pattern
    from tests/test_workspace.py). Clears any process-local pin so active_slug
    reads the registry we build here."""
    monkeypatch.setattr(workspace, "BASE_DIR", tmp_path)
    workspace.unpin_active()
    a = workspace.create_project("Project A", make_active=True)
    b = workspace.create_project("Project B")
    return a, b


def test_status_shape(client):
    body = client.get("/api/status").get_json()
    assert body["ok"] is True
    # version + theme are strings; project is a slug-or-None.
    assert isinstance(body["version"], str)
    assert body["theme"] in ("light", "dark")
    assert "project" in body


def test_project_list_shape_and_active(client, tmp_projects):
    a, b = tmp_projects
    body = client.get("/api/project").get_json()
    assert body["ok"] is True
    assert body["active"] == a
    slugs = {p["slug"] for p in body["projects"]}
    assert {a, b} <= slugs
    one = next(p for p in body["projects"] if p["slug"] == a)
    assert set(one.keys()) == {"slug", "name", "person", "daily"}


def test_project_switch(client, tmp_projects):
    a, b = tmp_projects
    resp = client.post("/api/project", json={"slug": b},
                       headers={"Origin": "http://127.0.0.1:5002"})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body == {"ok": True, "active": b}
    assert workspace.active_slug() == b


def test_project_switch_headerless_403(client, tmp_projects):
    """A mutating POST with NO Origin AND NO Referer is denied (strict decorator
    policy — parity with the receiver's _origin_allowed('') deny)."""
    a, b = tmp_projects
    resp = client.post("/api/project", json={"slug": b})
    assert resp.status_code == 403
    assert resp.get_json() == {"ok": False, "error": "forbidden origin"}
    # The switch was rejected before touching the registry.
    assert workspace.active_slug() == a


def test_project_switch_unknown_slug_400(client, tmp_projects):
    resp = client.post("/api/project", json={"slug": "does-not-exist"},
                       headers={"Origin": _EXT_ORIGIN})
    assert resp.status_code == 400
    assert resp.get_json()["ok"] is False
    # Active project unchanged.
    assert workspace.active_slug() == tmp_projects[0]


def test_project_switch_missing_slug_400(client, tmp_projects):
    resp = client.post("/api/project", json={},
                       headers={"Origin": _EXT_ORIGIN})
    assert resp.status_code == 400


def test_project_switch_foreign_origin_403(client, tmp_projects):
    a, b = tmp_projects
    resp = client.post("/api/project", json={"slug": b},
                       headers={"Origin": _FOREIGN_ORIGIN})
    assert resp.status_code == 403
    assert resp.get_json() == {"ok": False, "error": "forbidden origin"}
    # The switch was rejected before touching the registry.
    assert workspace.active_slug() == a


def test_project_switch_loopback_origin_allowed(client, tmp_projects):
    a, b = tmp_projects
    resp = client.post("/api/project", json={"slug": b},
                       headers={"Origin": "http://127.0.0.1:5002"})
    assert resp.status_code == 200
    assert workspace.active_slug() == b


def test_project_switch_under_pin_echoes_written_slug(client, tmp_projects):
    """While a pinned engine run holds project A, a switch to B must NOT report a
    silent no-op: active_slug() returns the pinned A, but the write to B DID take
    effect. The route echoes the persisted slug (B) + a ``pending_pinned`` note so
    the UI can explain the switch goes live once the run finishes. (finding #6)"""
    a, b = tmp_projects
    workspace.pin_active(a)          # simulate an in-flight run pinned to A
    try:
        resp = client.post("/api/project", json={"slug": b},
                           headers={"Origin": "http://127.0.0.1:5002"})
        assert resp.status_code == 200
        body = resp.get_json()
        # Echoes the slug we actually persisted (B), not the pinned live slug (A).
        assert body["active"] == b
        assert body["pending_pinned"] == a
        # The registry really was switched (the write was not a no-op)…
        assert workspace.registry_active_slug() == b
        # …even though live resolution still returns the pin until the run ends.
        assert workspace.active_slug() == a
    finally:
        workspace.unpin_active()
    # Once the pin releases, resolution catches up to the persisted switch.
    assert workspace.active_slug() == b
