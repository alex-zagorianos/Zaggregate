"""MINOR-2 (S36 scenario findings): every /api/* error — including routing-layer
404/405s that fire before any view runs — must carry the {ok:false, error} JSON
envelope, never Flask's default HTML page. Non-API paths keep default behavior.
"""
import json


def _body(resp) -> dict:
    assert resp.content_type.startswith("application/json"), resp.content_type
    return json.loads(resp.get_data(as_text=True))


def test_unknown_api_route_is_json_404(client):
    resp = client.get("/api/does-not-exist")
    assert resp.status_code == 404
    data = _body(resp)
    assert data["ok"] is False
    assert data["error"] == "not found"


def test_wrong_method_on_api_route_is_json_405(client):
    # /api/runs/daily is POST-only.
    resp = client.get("/api/runs/daily")
    assert resp.status_code == 405
    data = _body(resp)
    assert data["ok"] is False
    assert data["error"] == "method not allowed"


def test_literal_dotdot_download_path_is_json_404(client):
    # Werkzeug normalizes the literal ../ at the routing layer and 404s before
    # the download view's own containment check runs; the raw request path still
    # starts with /api/, so the envelope handler must shape it. Bypass the test
    # client's own path normalization by building the environ directly.
    resp = client.open(
        "/api/resume/download/x",
        method="GET",
        environ_overrides={
            "PATH_INFO": "/api/resume/download/../../../../windows/win.ini",
            "RAW_URI": "/api/resume/download/../../../../windows/win.ini",
        },
    )
    assert resp.status_code == 404
    data = _body(resp)
    assert data["ok"] is False
    assert data["error"] == "not found"


def test_non_api_404_keeps_default_shape(client):
    # The envelope is scoped to /api/*: a bogus non-API path still gets the
    # framework's default (non-JSON) 404 page.
    resp = client.get("/definitely-not-a-route")
    assert resp.status_code == 404
    assert not resp.content_type.startswith("application/json")
