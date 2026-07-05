"""POST /api/project/create — web create-project / new-person flow (B2).

The switch route (POST /api/project) is covered in test_system.py; this module
covers the CREATE route: validation (400), duplicate slug (409), origin gate
(403), the no-switch default, and the switch-integration path (registry active
moves; a pin is respected — the switch is persisted but pending, not blocked).
"""
import pytest

import workspace


_LOOPBACK = "http://127.0.0.1:5002"
_FOREIGN_ORIGIN = "https://evil.example.com"


@pytest.fixture
def tmp_projects(tmp_path, monkeypatch):
    """A fresh registry with one active project (mirrors test_system.py). Clears
    any process-local pin so active_slug reads the registry we build here."""
    monkeypatch.setattr(workspace, "BASE_DIR", tmp_path)
    workspace.unpin_active()
    a = workspace.create_project("Project A", make_active=True)
    return a


def _post(client, body, origin=_LOOPBACK):
    headers = {"Origin": origin} if origin else {}
    return client.post("/api/project/create", json=body, headers=headers)


def test_create_project_default_no_switch(client, tmp_projects):
    """A create WITHOUT switch adds the project but leaves the active one alone."""
    a = tmp_projects
    resp = _post(client, {"name": "Marketing Roles"})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert body["slug"] == "marketing-roles"
    # Not switched: the active project is unchanged and the response echoes it.
    assert body["active"] == a
    assert workspace.registry_active_slug() == a
    # The new project is present in the returned list with the summary shape.
    new = next(p for p in body["projects"] if p["slug"] == "marketing-roles")
    assert set(new.keys()) == {"slug", "name", "person", "daily"}
    assert new["name"] == "Marketing Roles"
    assert new["person"] is None


def test_create_project_with_switch_navigates_active(client, tmp_projects):
    """switch:true makes the new project active (the dialog default)."""
    resp = _post(client, {"name": "Design Search", "switch": True})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert body["slug"] == "design-search"
    assert body["active"] == "design-search"
    assert workspace.active_slug() == "design-search"
    assert "pending_pinned" not in body


def test_create_project_with_person(client, tmp_projects):
    """A person tag rides through to the registry entry (new-person flow)."""
    resp = _post(client, {"name": "Dad Search", "person": "Dad", "switch": True})
    assert resp.status_code == 200
    body = resp.get_json()
    new = next(p for p in body["projects"] if p["slug"] == "dad-search")
    assert new["person"] == "Dad"


def test_create_project_blank_person_is_unassigned(client, tmp_projects):
    """A blank/whitespace person is treated as unassigned (None), not "" — so the
    registry stays back-compatible (person omitted for single-person installs)."""
    resp = _post(client, {"name": "Solo Search", "person": "   "})
    body = resp.get_json()
    new = next(p for p in body["projects"] if p["slug"] == "solo-search")
    assert new["person"] is None


def test_create_project_empty_name_400(client, tmp_projects):
    for bad in ({"name": ""}, {"name": "   "}, {}):
        resp = _post(client, bad)
        assert resp.status_code == 400
        assert resp.get_json()["ok"] is False


def test_create_project_duplicate_slug_409(client, tmp_projects):
    """A name mapping to an existing slug is a 409 with the exact contract error —
    never a silent re-activate/overwrite of the other project."""
    a = tmp_projects  # slug "project-a" from "Project A"
    # Different spelling, same slug.
    resp = _post(client, {"name": "PROJECT a!"})
    assert resp.status_code == 409
    body = resp.get_json()
    assert body == {"ok": False, "error": "a project with that name already exists"}
    # The existing project was untouched (still the only Project A entry).
    slugs = [p["slug"] for p in workspace.list_projects()]
    assert slugs.count(a) == 1


def test_create_project_headerless_403(client, tmp_projects):
    """A mutating POST with no Origin/Referer is denied before touching the
    registry (route-audit parity)."""
    resp = _post(client, {"name": "Should Not Exist"}, origin=None)
    assert resp.status_code == 403
    assert resp.get_json() == {"ok": False, "error": "forbidden origin"}
    assert "should-not-exist" not in {p["slug"] for p in workspace.list_projects()}


def test_create_project_foreign_origin_403(client, tmp_projects):
    resp = _post(client, {"name": "Should Not Exist"}, origin=_FOREIGN_ORIGIN)
    assert resp.status_code == 403
    assert resp.get_json() == {"ok": False, "error": "forbidden origin"}
    assert "should-not-exist" not in {p["slug"] for p in workspace.list_projects()}


def test_create_project_switch_under_pin_is_pending(client, tmp_projects):
    """Creating+switching while a run pins a DIFFERENT project: the switch is
    persisted (registry moves) but live resolution stays on the pin until the run
    releases it, surfaced via ``pending_pinned`` (mirrors the switch route's
    exclusive-run guard — the switch is never blocked, only pending). (finding #6)"""
    a = tmp_projects
    workspace.pin_active(a)  # simulate an in-flight run pinned to A
    try:
        resp = _post(client, {"name": "Nights Only", "switch": True})
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["slug"] == "nights-only"
        # Persisted switch to the new project…
        assert body["active"] == "nights-only"
        assert body["pending_pinned"] == a
        assert workspace.registry_active_slug() == "nights-only"
        # …but live resolution still returns the pin until the run ends.
        assert workspace.active_slug() == a
    finally:
        workspace.unpin_active()
    assert workspace.active_slug() == "nights-only"



def test_create_no_switch_on_fresh_registry_keeps_active_off_new_project(
        client, tmp_path, monkeypatch):
    """S37 Phase-1 review CRITICAL regression (end-to-end, mirrors the
    verifier's repro): on a truly FRESH registry (no projects.json), POST
    /project/create with switch:false must not silently activate the new
    project when any other project (the default root) is registered."""
    monkeypatch.setattr(workspace, "BASE_DIR", tmp_path)
    workspace.unpin_active()

    resp = _post(client, {"name": "My First Search", "switch": False})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True and body["slug"] == "my-first-search"

    others = [p["slug"] for p in body["projects"] if p["slug"] != "my-first-search"]
    if others:
        # The repair must prefer an existing project (default root), never the
        # explicitly-not-switched new one.
        assert body["active"] != "my-first-search"
        assert workspace.registry_active_slug() != "my-first-search"
    else:
        # Sole-project fallback is the one allowed case.
        assert body["active"] == "my-first-search"
