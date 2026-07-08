"""Search Discovery API (webui.api.discovery) — route shapes + the cfg-mirroring
contract. The cross-cutting origin-gate audit lives in test_route_audit.py (it
enumerates url_map); here we assert per-route behavior with an isolated cfg."""
import pytest

import workspace
from tracker import db


_LOOPBACK = {"Origin": "http://127.0.0.1:5002"}


@pytest.fixture
def cfg_store(monkeypatch):
    """In-memory search config so activate/deactivate/excludes writes are hermetic
    (never touch the real project). Also no-op the project pin so the routes don't
    stamp a marker into a real project dir during the test."""
    store = {"keywords": []}
    monkeypatch.setattr(workspace, "load_config", lambda slug=None: dict(store))
    monkeypatch.setattr(workspace, "save_config", lambda cfg, slug=None: store.update(cfg))
    monkeypatch.setattr(workspace, "active_slug", lambda: "test")
    monkeypatch.setattr(workspace, "pin_active", lambda slug=None: None)
    monkeypatch.setattr(workspace, "unpin_active", lambda: None)
    return store


def test_propose_route_shape_and_seeds_pool(client, tmp_db, cfg_store):
    r = client.get("/api/discovery/propose?field=welder")
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is True
    assert body["resolved_soc"]
    assert body["core"] and body["adjacent"]          # real tiers for a resolvable field
    # propose seeds the pool as a side effect, so /pool now reflects it
    pool_body = client.get("/api/discovery/pool").get_json()
    terms = {row["term"] for row in pool_body["pool"]}
    assert terms                                        # something got persisted
    assert all(row["status"] == "suggested" for row in pool_body["pool"])


def test_keyword_typeahead(client, tmp_db, cfg_store):
    body = client.get("/api/discovery/keywords?q=mechan&limit=5").get_json()
    assert body["ok"] is True
    assert len(body["suggestions"]) <= 5
    assert body["suggestions"]                          # prefix 'mechan' matches something


def test_activate_mirrors_into_cfg_keywords(client, tmp_db, cfg_store):
    r = client.post("/api/discovery/keywords/activate",
                    json={"term": "Diesel Mechanic", "tier": "core", "source": "onet"},
                    headers=_LOOPBACK)
    assert r.status_code == 200
    assert "Diesel Mechanic" in r.get_json()["keywords"]
    assert "Diesel Mechanic" in cfg_store["keywords"]      # mirrored into the search config
    assert cfg_store["discovery_enabled"] is True
    from search.discovery import pool
    assert pool.get_term("Diesel Mechanic")["status"] == "active"


def test_deactivate_removes_from_cfg_keywords(client, tmp_db, cfg_store):
    client.post("/api/discovery/keywords/activate", json={"term": "Welder"},
                headers=_LOOPBACK)
    assert "Welder" in cfg_store["keywords"]
    r = client.post("/api/discovery/keywords/deactivate", json={"term": "Welder"},
                    headers=_LOOPBACK)
    assert r.status_code == 200
    assert "Welder" not in cfg_store["keywords"]
    from search.discovery import pool
    assert pool.get_term("Welder")["status"] == "inactive"


def test_excludes_add_and_remove(client, tmp_db, cfg_store):
    client.post("/api/discovery/excludes",
                json={"term": "commission only", "action": "add"}, headers=_LOOPBACK)
    assert cfg_store["suggested_excludes"] == ["commission only"]
    client.post("/api/discovery/excludes",
                json={"term": "commission only", "action": "remove"}, headers=_LOOPBACK)
    assert cfg_store["suggested_excludes"] == []


def test_probe_route_no_key_is_graceful(client, tmp_db, cfg_store, monkeypatch):
    # Adzuna unconfigured -> each probe comes back skipped, never a 500, no network.
    import config
    monkeypatch.setattr(config, "resolve_secret", lambda *a, **k: "")
    r = client.post("/api/discovery/probe",
                    json={"terms": ["Diesel Mechanic"], "location": "Cincinnati, OH"},
                    headers=_LOOPBACK)
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is True
    assert body["results"][0]["skipped"] is True


def test_probe_requires_origin(client, tmp_db, cfg_store):
    # Header-less mutating call is gate-rejected (the meta-audit covers all routes;
    # this is a direct smoke check on the discovery module).
    r = client.post("/api/discovery/probe", json={"terms": ["x"]})
    assert r.status_code == 403


def test_mine_flips_discovery_enabled(client, tmp_db, cfg_store):
    r = client.post("/api/discovery/mine", headers=_LOOPBACK)
    assert r.status_code == 200
    assert r.get_json()["ok"] is True
    assert cfg_store["discovery_enabled"] is True
