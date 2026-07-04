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


_SECRET = "TOP-SECRET-OUT-OF-ROOT"


@pytest.fixture
def built_static_with_secret(tmp_path, monkeypatch):
    """A built static dir (with index.html + a real asset) plus a secret file that
    lives OUTSIDE the static root (in its parent), so a traversal that escaped the
    root would leak it."""
    root = tmp_path / "static"
    root.mkdir()
    (root / "index.html").write_text("<!doctype html><title>Zaggregate</title>",
                                     encoding="utf-8")
    (root / "app.js").write_text("console.log('hi')", encoding="utf-8")
    # Sibling of the static root -> reachable only via a successful ".." escape.
    (tmp_path / "secret.txt").write_text(_SECRET, encoding="utf-8")
    monkeypatch.setattr(paths, "static_dir", lambda: root)
    return root


@pytest.mark.parametrize("path", [
    "/app/../secret.txt",
    "/app/%2e%2e/secret.txt",
    "/app/..%5Csecret.txt",
    "/app/..%2fsecret.txt",
    "/app/%2e%2e%2fsecret.txt",
    "/app/....//secret.txt",
])
def test_traversal_never_leaks_out_of_root_secret(client, built_static_with_secret, path):
    """No path-traversal spelling may return the out-of-root secret's content.
    send_from_directory is the single traversal authority; a 404 or an index.html
    SPA fallback are both acceptable outcomes — leaking the secret is not."""
    resp = client.get(path)
    body = resp.get_data()
    assert _SECRET.encode() not in body, (path, resp.status_code)
    # And it must NOT be a 200 that served the secret file directly.
    assert resp.status_code in (200, 404)
    if resp.status_code == 200:
        # A 200 here can only be the SPA index.html fallback, never the secret.
        assert b"Zaggregate" in body


def test_traversal_absolute_path_never_leaks(client, built_static_with_secret, tmp_path):
    """An absolute-path variant pointing at the secret must not return it."""
    secret_abs = str((tmp_path / "secret.txt").resolve())
    resp = client.get(f"/app/{secret_abs}")
    assert _SECRET.encode() not in resp.get_data()
    assert resp.status_code in (200, 404)


def test_static_available_reflects_index(monkeypatch, tmp_path):
    d = tmp_path / "static"
    monkeypatch.setattr(paths, "static_dir", lambda: d)
    assert paths.static_available() is False
    d.mkdir()
    assert paths.static_available() is False  # dir but no index
    (d / "index.html").write_text("x", encoding="utf-8")
    assert paths.static_available() is True
