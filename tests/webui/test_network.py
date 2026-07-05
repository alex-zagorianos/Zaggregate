"""Referral-network routes + detail enrichment + warm-path prompt (B4).

* /api/network/import|summary|clear|company/<name>  (gating, size cap, roundtrip)
* /api/inbox/<id>/detail                             carries the `network` block
* /api/inbox/<id>/warm-path-prompt                   prompt content
* /api/applications/<id>/detail + warm-path-prompt   network block + prompt
"""
import json

import pytest

import config
import network as networkmod
import workspace


_H = {"Origin": "http://127.0.0.1:5002"}

_LINKEDIN = (
    "First Name,Last Name,Company,Position\n"
    "Jane,Doe,Acme Inc.,Staff Engineer\n"
    "John,Roe,ACME,Recruiter\n"
)


@pytest.fixture(autouse=True)
def _tmp_network(tmp_path, monkeypatch):
    """Isolate the user-level network store + the experience/config the warm-path
    builder reads, so nothing touches real user data."""
    monkeypatch.setattr(config, "USER_DATA_DIR", tmp_path)
    exp = tmp_path / "experience.md"
    exp.write_text(
        "## EDUCATION\nB.S. ME, State Polytechnic University\n\n"
        "## WORK EXPERIENCE\nControls Engineer, Globex Corporation\n",
        encoding="utf-8")
    monkeypatch.setattr(workspace, "experience_file", lambda slug=None: exp)
    monkeypatch.setattr(workspace, "load_config",
                        lambda slug=None: {"location": "Cincinnati, OH"})
    return tmp_path


# ── import / summary / clear / company ─────────────────────────────────────────

def test_import_then_summary_and_company(client):
    r = client.post("/api/network/import", headers=_H,
                    json={"text": _LINKEDIN, "source": "linkedin"})
    body = r.get_json()
    assert r.status_code == 200 and body["ok"] is True
    assert body["added"] == 2 and body["total"] == 2

    r = client.get("/api/network/summary")
    s = r.get_json()
    assert s["ok"] is True and s["total"] == 2 and s["companies"] == 1
    assert s["last_import"]["source"] == "linkedin"

    # Company lookup is canonical (Acme Inc. == ACME).
    r = client.get("/api/network/company/Acme")
    got = r.get_json()
    assert got["ok"] is True
    assert {c["name"] for c in got["contacts"]} == {"Jane Doe", "John Roe"}

    # Clear empties it.
    r = client.post("/api/network/clear", headers=_H)
    assert r.get_json() == {"ok": True, "removed": 2}
    assert client.get("/api/network/summary").get_json()["total"] == 0


def test_import_missing_text_is_400(client):
    r = client.post("/api/network/import", headers=_H, json={"source": "linkedin"})
    assert r.status_code == 400
    assert r.get_json()["ok"] is False


def test_import_oversized_body_is_400(client):
    big = "First Name,Company\n" + ("x" * (5 * 1024 * 1024 + 10))
    r = client.post("/api/network/import", headers=_H,
                    json={"text": big, "source": "linkedin"})
    assert r.status_code == 400
    assert "too large" in r.get_json()["error"]


def test_import_and_clear_are_origin_gated(client):
    assert client.post("/api/network/import", json={"text": _LINKEDIN}).status_code == 403
    assert client.post("/api/network/clear", json={}).status_code == 403


def test_unknown_source_coerces_to_linkedin(client):
    r = client.post("/api/network/import", headers=_H,
                    json={"text": _LINKEDIN, "source": "bogus"})
    assert r.status_code == 200
    assert networkmod.summary()["last_import"]["source"] == "linkedin"


# ── inbox detail enrichment + warm-path ────────────────────────────────────────

def _first_demo_row(client):
    """A demo inbox row id (negative id) — the read routes serve demo rows when the
    real inbox is empty, so no DB seeding is needed for the detail-pane tests."""
    rows = client.get("/api/inbox").get_json()["rows"]
    return rows[0] if rows else None


def test_inbox_detail_carries_network_block(client):
    row = _first_demo_row(client)
    assert row is not None
    # Seed the network with contacts at this row's company so a match exists.
    networkmod.import_text(
        f"First Name,Last Name,Company,Position\nPat,Lee,{row['company']},Engineer\n",
        "linkedin")
    detail = client.get(f"/api/inbox/{row['id']}/detail").get_json()
    assert detail["ok"] is True
    assert "network" in detail
    assert detail["network"]["count"] == 1
    assert detail["network"]["contacts"][0]["name"] == "Pat Lee"


def test_inbox_detail_network_empty_when_no_match(client):
    row = _first_demo_row(client)
    detail = client.get(f"/api/inbox/{row['id']}/detail").get_json()
    assert detail["network"] == {"count": 0, "contacts": []}


def test_inbox_warm_path_prompt(client):
    row = _first_demo_row(client)
    r = client.get(f"/api/inbox/{row['id']}/warm-path-prompt")
    body = r.get_json()
    assert r.status_code == 200 and body["ok"] is True
    assert "Warm paths, ranked" in body["prompt"]
    assert row["company"] in body["prompt"]
    # Experience mining flowed in.
    assert "State Polytechnic University" in body["prompt"]


def test_inbox_warm_path_unknown_id_404(client):
    r = client.get("/api/inbox/987654/warm-path-prompt")
    assert r.status_code == 404


# ── application detail enrichment + warm-path ──────────────────────────────────

def test_application_detail_and_warm_path(client, tmp_db):
    from tracker import service
    app_id = service.add_manual_job(title="Senior Controls Engineer",
                                    company="Acme Robotics")
    networkmod.import_text(
        "First Name,Last Name,Company,Position\nJane,Doe,Acme Robotics,Staff Eng\n",
        "linkedin")

    detail = client.get(f"/api/applications/{app_id}").get_json()
    assert detail["ok"] is True
    assert detail["network"]["count"] == 1
    assert detail["network"]["contacts"][0]["name"] == "Jane Doe"

    r = client.get(f"/api/applications/{app_id}/warm-path-prompt")
    body = r.get_json()
    assert r.status_code == 200 and body["ok"] is True
    assert "Acme Robotics" in body["prompt"]
    assert "Jane Doe" in body["prompt"]


def test_application_warm_path_unknown_id_404(client, tmp_db):
    r = client.get("/api/applications/987654/warm-path-prompt")
    assert r.status_code == 404
