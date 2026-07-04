"""/api/settings/theme — get, put, invalid 400, origin 403, persistence."""
import pytest

import config
from ui import settings as ui_settings


_EXT_ORIGIN = "chrome-extension://abcdefghijklmnop"
_FOREIGN_ORIGIN = "https://evil.example.com"


@pytest.fixture
def tmp_settings(tmp_path, monkeypatch):
    """Point ui.settings at a tmp user-data dir so theme writes don't touch the
    real ui_settings.json."""
    monkeypatch.setattr(config, "USER_DATA_DIR", tmp_path)
    return tmp_path


def test_get_theme_default(client, tmp_settings):
    body = client.get("/api/settings/theme").get_json()
    assert body["ok"] is True
    assert body["mode"] == "light"  # default when unset


def test_put_theme_persists(client, tmp_settings):
    resp = client.put("/api/settings/theme", json={"mode": "dark"},
                      headers={"Origin": "http://127.0.0.1:5002"})
    assert resp.status_code == 200
    assert resp.get_json() == {"ok": True, "mode": "dark"}
    # Persisted through ui.settings (reads it back independently).
    assert ui_settings.get_theme() == "dark"
    assert client.get("/api/settings/theme").get_json()["mode"] == "dark"


def test_put_theme_loopback_origin_allowed(client, tmp_settings):
    """The loopback-Origin happy path passes the strict mutating-origin gate."""
    resp = client.put("/api/settings/theme", json={"mode": "dark"},
                      headers={"Origin": "http://127.0.0.1:5002"})
    assert resp.status_code == 200
    assert ui_settings.get_theme() == "dark"


def test_put_theme_headerless_403(client, tmp_settings):
    """A mutating PUT with NO Origin AND NO Referer is denied (strict decorator
    policy — nothing is persisted)."""
    resp = client.put("/api/settings/theme", json={"mode": "dark"})
    assert resp.status_code == 403
    assert resp.get_json() == {"ok": False, "error": "forbidden origin"}
    assert ui_settings.get_theme() == "light"


def test_put_theme_invalid_400(client, tmp_settings):
    resp = client.put("/api/settings/theme", json={"mode": "neon"},
                      headers={"Origin": _EXT_ORIGIN})
    assert resp.status_code == 400
    assert resp.get_json()["ok"] is False
    # Nothing persisted.
    assert ui_settings.get_theme() == "light"


def test_put_theme_foreign_origin_403(client, tmp_settings):
    resp = client.put("/api/settings/theme", json={"mode": "dark"},
                      headers={"Origin": _FOREIGN_ORIGIN})
    assert resp.status_code == 403
    assert resp.get_json() == {"ok": False, "error": "forbidden origin"}
    assert ui_settings.get_theme() == "light"
