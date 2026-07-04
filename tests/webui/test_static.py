"""Static /app serving — 503 when unbuilt, serves from a tmp static dir, SPA fallback."""
import pytest

from webui import paths


def test_app_503_when_unbuilt(client, monkeypatch, tmp_path):
    """With no built frontend, /app degrades to 503 rather than 404-ing on a
    missing dir."""
    empty = tmp_path / "static"  # does not exist
    monkeypatch.setattr(paths, "static_dir", lambda: empty)
    resp = client.get("/app")
    assert resp.status_code == 503
    assert resp.get_json() == {"ok": False, "error": "web UI not built"}


@pytest.fixture
def built_static(tmp_path, monkeypatch):
    """A tmp static dir standing in for a built frontend."""
    d = tmp_path / "static"
    d.mkdir()
    (d / "index.html").write_text("<!doctype html><title>Zaggregate</title>",
                                  encoding="utf-8")
    (d / "app.js").write_text("console.log('hi')", encoding="utf-8")
    assets = d / "assets"
    assets.mkdir()
    (assets / "main.css").write_text("body{}", encoding="utf-8")
    monkeypatch.setattr(paths, "static_dir", lambda: d)
    return d


def test_app_index_served(client, built_static):
    resp = client.get("/app")
    assert resp.status_code == 200
    assert b"Zaggregate" in resp.get_data()


def test_app_real_asset_served(client, built_static):
    resp = client.get("/app/app.js")
    assert resp.status_code == 200
    assert b"console.log" in resp.get_data()


def test_app_nested_asset_served(client, built_static):
    resp = client.get("/app/assets/main.css")
    assert resp.status_code == 200
    assert b"body{}" in resp.get_data()


def test_app_spa_fallback_to_index(client, built_static):
    """An unknown client-route path (no matching file) falls back to index.html
    so the SPA router handles it, rather than 404."""
    resp = client.get("/app/inbox/some/deep/route")
    assert resp.status_code == 200
    assert b"Zaggregate" in resp.get_data()


def test_static_available_reflects_index(monkeypatch, tmp_path):
    d = tmp_path / "static"
    monkeypatch.setattr(paths, "static_dir", lambda: d)
    assert paths.static_available() is False
    d.mkdir()
    assert paths.static_available() is False  # dir but no index
    (d / "index.html").write_text("x", encoding="utf-8")
    assert paths.static_available() is True
