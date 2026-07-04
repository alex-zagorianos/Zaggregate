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
                       headers={"Origin": _EXT_ORIGIN})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body == {"ok": True, "active": b}
    assert workspace.active_slug() == b


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
