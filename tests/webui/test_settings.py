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


# ── /api/settings/keys ────────────────────────────────────────────────────────

_LOOPBACK = "http://127.0.0.1:5002"

_SOURCE_ENV_VARS = (
    "ADZUNA_APP_ID", "ADZUNA_APP_KEY", "USAJOBS_API_KEY", "USAJOBS_EMAIL",
    "JOOBLE_API_KEY", "CAREERJET_AFFID", "CAREERONESTOP_USER_ID",
    "CAREERONESTOP_TOKEN",
)


@pytest.fixture
def tmp_secrets(tmp_path, monkeypatch):
    """Point config.SECRETS_DIR at a tmp dir and strip any source env vars so a
    dev machine's real .env can't shadow the seeded test secret (env wins over the
    secret file by design — see ui/settings.get_api_key)."""
    monkeypatch.setattr(config, "SECRETS_DIR", tmp_path / "secrets")
    for var in _SOURCE_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    return tmp_path / "secrets"


def test_keys_list_shape_all_unset(client, tmp_secrets):
    body = client.get("/api/settings/keys").get_json()
    assert body["ok"] is True
    ids = {s["id"] for s in body["sources"]}
    assert ids == {"adzuna", "usajobs", "jooble", "careerjet", "careeronestop"}
    for s in body["sources"]:
        assert s["label"] and s["get_key_url"].startswith("http")
        assert s["impact"]                       # the reach line the card shows
        for f in s["fields"]:
            assert f["set"] is False
            assert f["masked"] is None           # unset -> no mask, no value


def test_keys_list_masks_set_key_last4_only(client, tmp_secrets):
    # Seed a key through the SAME mechanism the app uses.
    ui_settings.set_api_key("adzuna_app_id", "abcd1234")
    body = client.get("/api/settings/keys").get_json()
    adzuna = next(s for s in body["sources"] if s["id"] == "adzuna")
    app_id = next(f for f in adzuna["fields"] if f["name"] == "adzuna_app_id")
    assert app_id["set"] is True
    assert app_id["masked"] == "••••1234"        # last-4 only
    # The raw value must appear NOWHERE in the serialized response.
    import json as _json
    assert "abcd1234" not in _json.dumps(body)


def test_keys_put_persists_and_returns_saved(client, tmp_secrets):
    resp = client.put("/api/settings/keys/adzuna",
                      json={"adzuna_app_id": "deadbeef",
                            "adzuna_app_key": "f" * 32},
                      headers={"Origin": _LOOPBACK})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert set(body["saved"]) == {"adzuna_app_id", "adzuna_app_key"}
    assert body["warnings"] == []                # both are >=8 chars
    # Persisted through the secrets/ mechanism.
    assert ui_settings.get_api_key("adzuna_app_id") == "deadbeef"


def test_keys_put_shape_warning_non_blocking(client, tmp_secrets):
    # A too-short value (<8 chars) trips looks_like_key but is STILL saved
    # (inclusion over precision — the warning is advisory, not a block).
    resp = client.put("/api/settings/keys/careerjet",
                      json={"careerjet_affid": "ab"},
                      headers={"Origin": _LOOPBACK})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["saved"] == ["careerjet_affid"]
    assert body["warnings"] and body["warnings"][0]["field"] == "careerjet_affid"
    assert ui_settings.get_api_key("careerjet_affid") == "ab"   # saved anyway


def test_keys_put_ignores_unknown_field(client, tmp_secrets):
    resp = client.put("/api/settings/keys/jooble",
                      json={"jooble_api_key": "x" * 10, "bogus": "nope"},
                      headers={"Origin": _LOOPBACK})
    body = resp.get_json()
    assert body["saved"] == ["jooble_api_key"]   # bogus ignored, not saved


def test_keys_put_unknown_source_404(client, tmp_secrets):
    resp = client.put("/api/settings/keys/nosuch", json={"x": "y"},
                      headers={"Origin": _LOOPBACK})
    assert resp.status_code == 404
    assert resp.get_json()["ok"] is False


def test_keys_put_origin_gated_403(client, tmp_secrets):
    resp = client.put("/api/settings/keys/adzuna",
                      json={"adzuna_app_id": "deadbeef"})   # no Origin
    assert resp.status_code == 403
    assert ui_settings.get_api_key("adzuna_app_id") == ""    # nothing persisted


def test_keys_test_route_noop_under_pytest(client, tmp_secrets):
    # The live probe self-skips under pytest -> the route returns the no-op shape.
    resp = client.post("/api/settings/keys/adzuna/test",
                       headers={"Origin": _LOOPBACK})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert body["result"]["status"] == "failed"
    assert body["result"]["detail"] == "skipped (test mode)"


def test_keys_test_unknown_source_404(client, tmp_secrets):
    resp = client.post("/api/settings/keys/nosuch/test",
                       headers={"Origin": _LOOPBACK})
    assert resp.status_code == 404


def test_keys_test_origin_gated_403(client, tmp_secrets):
    resp = client.post("/api/settings/keys/adzuna/test")   # no Origin
    assert resp.status_code == 403


def test_adzuna_split_happy(client, tmp_secrets):
    blob = "Application ID: 1a2b3c4d\nApplication Key: " + "f" * 32
    resp = client.post("/api/settings/keys/adzuna/split",
                       json={"clipboard": blob}, headers={"Origin": _LOOPBACK})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert body["app_id"] == "1a2b3c4d"
    assert body["app_key"] == "f" * 32


def test_adzuna_split_no_match(client, tmp_secrets):
    resp = client.post("/api/settings/keys/adzuna/split",
                       json={"clipboard": "no credentials here"},
                       headers={"Origin": _LOOPBACK})
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is False


def test_adzuna_split_origin_gated_403(client, tmp_secrets):
    resp = client.post("/api/settings/keys/adzuna/split",
                       json={"clipboard": "deadbeef " + "a" * 32})   # no Origin
    assert resp.status_code == 403
