"""/api/inbox/<id>/track and /dismiss — happy path, 404 unknown, 403 origin.

Seeds an inbox row in a tmp DB (the shared ``tmp_db`` fixture), then exercises the
two triage mutations that move a row OUT of the inbox. Mutating happy-paths send a
loopback Origin so they pass the strict origin gate; the header-less case asserts
the 403 (and that nothing was mutated).
"""
from models import JobResult
from tracker import db, service


_LOOPBACK = "http://127.0.0.1:5002"


def _job(url, title="Software Developer", company="Acme"):
    return JobResult(title=title, company=company, location="Cincinnati, OH",
                     salary_min=None, salary_max=None, description="controls",
                     url=url, source_keyword="", created="2026-06-21",
                     source_api="adzuna", score=70)


def _seed_one(url="https://x/1") -> int:
    db.inbox_add_many([_job(url)])
    return db.inbox_all()[0]["id"]


# ── track ─────────────────────────────────────────────────────────────────────

def test_track_happy_path(client, tmp_db):
    inbox_id = _seed_one()
    resp = client.post(f"/api/inbox/{inbox_id}/track",
                       headers={"Origin": _LOOPBACK})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert isinstance(body["app_id"], int) and body["app_id"] > 0
    # The row left the inbox and landed in the tracker as a real application.
    assert db.inbox_count() == 0
    assert service.get_job(body["app_id"]) is not None


def test_track_unknown_id_404(client, tmp_db):
    resp = client.post("/api/inbox/999999/track", headers={"Origin": _LOOPBACK})
    assert resp.status_code == 404
    assert resp.get_json()["ok"] is False


def test_track_headerless_403(client, tmp_db):
    inbox_id = _seed_one()
    resp = client.post(f"/api/inbox/{inbox_id}/track")  # no Origin/Referer
    assert resp.status_code == 403
    assert resp.get_json() == {"ok": False, "error": "forbidden origin"}
    # Nothing tracked, row still present.
    assert db.inbox_count() == 1


def test_track_foreign_origin_403(client, tmp_db):
    inbox_id = _seed_one()
    resp = client.post(f"/api/inbox/{inbox_id}/track",
                       headers={"Origin": "https://evil.example.com"})
    assert resp.status_code == 403
    assert db.inbox_count() == 1


# ── dismiss ───────────────────────────────────────────────────────────────────

def test_dismiss_happy_path(client, tmp_db):
    inbox_id = _seed_one()
    resp = client.post(f"/api/inbox/{inbox_id}/dismiss",
                       headers={"Origin": _LOOPBACK})
    assert resp.status_code == 200
    assert resp.get_json() == {"ok": True}
    assert db.inbox_count() == 0


def test_dismiss_unknown_id_404(client, tmp_db):
    resp = client.post("/api/inbox/999999/dismiss", headers={"Origin": _LOOPBACK})
    assert resp.status_code == 404
    assert resp.get_json()["ok"] is False


def test_dismiss_headerless_403(client, tmp_db):
    inbox_id = _seed_one()
    resp = client.post(f"/api/inbox/{inbox_id}/dismiss")  # no Origin/Referer
    assert resp.status_code == 403
    assert resp.get_json() == {"ok": False, "error": "forbidden origin"}
    assert db.inbox_count() == 1


def test_inbox_exists_helper(tmp_db):
    inbox_id = _seed_one()
    assert service.inbox_exists(inbox_id) is True
    assert service.inbox_exists(inbox_id + 12345) is False
