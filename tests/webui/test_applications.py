"""Applications (tracker) API — Phase 2 CRUD, validation, origin gate, rounds, ics.

Exercises the full ``/api/applications*`` surface against a tmp DB (the shared
``tmp_db`` fixture). Every mutating route is checked for the header-less 403; the
happy paths send a loopback Origin so they clear the strict origin gate. The
``.ics`` download asserts the attachment header + VEVENT content.
"""
from tracker import db, service


_LOOPBACK = "http://127.0.0.1:5002"
_H = {"Origin": _LOOPBACK}


def _add(title="Software Developer", company="Acme", **extra) -> int:
    """Seed one manual application straight through the service, returning its id."""
    return service.add_manual_job(title=title, company=company, **extra)


# ── list + counts ─────────────────────────────────────────────────────────────

def test_list_empty(client, tmp_db):
    resp = client.get("/api/applications")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert body["rows"] == []
    assert body["counts"]["all"] == 0
    assert body["followups_due"] == 0


def test_list_returns_rows_and_counts(client, tmp_db):
    _add(company="Acme")
    _add(title="QA", company="Globex")
    resp = client.get("/api/applications")
    body = resp.get_json()
    assert len(body["rows"]) == 2
    assert body["counts"]["all"] == 2
    assert body["counts"]["interested"] == 2
    # app_row serialization: known engine columns present.
    assert {"id", "title", "company", "status"} <= set(body["rows"][0])


def test_list_status_filter(client, tmp_db):
    a = _add(company="Acme")
    _add(title="QA", company="Globex")
    service.set_status(a, "applied")
    resp = client.get("/api/applications?status=applied")
    rows = resp.get_json()["rows"]
    assert [r["id"] for r in rows] == [a]


def test_list_archived_view(client, tmp_db):
    a = _add(company="Acme")
    _add(title="QA", company="Globex")
    service.archive_job(a)
    # Default view hides the archived row...
    default_rows = client.get("/api/applications").get_json()["rows"]
    assert a not in [r["id"] for r in default_rows]
    # ...the archived view shows only it.
    arch_rows = client.get("/api/applications?status=archived").get_json()["rows"]
    assert [r["id"] for r in arch_rows] == [a]


# ── add ───────────────────────────────────────────────────────────────────────

def test_add_happy_path(client, tmp_db):
    resp = client.post("/api/applications",
                       json={"title": "Controls Engineer", "company": "Acme"},
                       headers=_H)
    assert resp.status_code == 201
    body = resp.get_json()
    assert body["ok"] is True
    assert isinstance(body["id"], int) and body["id"] > 0
    assert service.get_job(body["id"])["title"] == "Controls Engineer"


def test_add_missing_title_400(client, tmp_db):
    resp = client.post("/api/applications", json={"company": "Acme"}, headers=_H)
    assert resp.status_code == 400
    assert resp.get_json()["ok"] is False
    assert db.get_counts()["all"] == 0


def test_add_missing_company_400(client, tmp_db):
    resp = client.post("/api/applications", json={"title": "Dev"}, headers=_H)
    assert resp.status_code == 400
    assert db.get_counts()["all"] == 0


def test_add_headerless_403(client, tmp_db):
    resp = client.post("/api/applications",
                       json={"title": "Dev", "company": "Acme"})  # no Origin
    assert resp.status_code == 403
    assert resp.get_json() == {"ok": False, "error": "forbidden origin"}
    assert db.get_counts()["all"] == 0


# ── get one (JobDialog payload) ───────────────────────────────────────────────

def test_get_one_shape(client, tmp_db):
    a = _add(company="Acme")
    resp = client.get(f"/api/applications/{a}")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert body["job"]["id"] == a
    assert body["timeline"] == []
    assert body["rounds"] == []
    assert body["referral"] == ""  # no contacts known
    assert body["statuses"] == db.STATUSES
    assert body["status_labels"] == db.STATUS_LABELS


def test_get_one_referral_hint(client, tmp_db):
    a = _add(company="Acme")
    db.add_contact("Jane Doe", company="Acme")
    body = client.get(f"/api/applications/{a}").get_json()
    assert "Jane Doe" in body["referral"]


def test_get_one_carries_ghosted_before(client, tmp_db):
    """The JobDialog payload surfaces prior ghostings at the same company (B7)."""
    from tracker import service
    a = _add(company="Acme")
    service.add_manual_job(title="Old", company="Acme", status="ghosted")
    body = client.get(f"/api/applications/{a}").get_json()
    assert body["ghosted_before"] == {"count": 1}


def test_get_one_ghosted_before_zero_for_clean_company(client, tmp_db):
    a = _add(company="Acme")
    body = client.get(f"/api/applications/{a}").get_json()
    assert body["ghosted_before"] == {"count": 0}


def test_get_one_404(client, tmp_db):
    resp = client.get("/api/applications/999999")
    assert resp.status_code == 404
    assert resp.get_json()["ok"] is False


# ── patch (update) ────────────────────────────────────────────────────────────

def test_patch_happy_path(client, tmp_db):
    a = _add(company="Acme")
    resp = client.patch(f"/api/applications/{a}",
                        json={"notes": "phoned back", "location": "Cincinnati"},
                        headers=_H)
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert body["job"]["notes"] == "phoned back"
    assert body["job"]["location"] == "Cincinnati"


def test_patch_unknown_field_400_names_field(client, tmp_db):
    a = _add(company="Acme")
    resp = client.patch(f"/api/applications/{a}",
                        json={"offer_salary": "120k"}, headers=_H)
    assert resp.status_code == 400
    err = resp.get_json()
    assert err["ok"] is False
    assert "offer_salary" in err["error"]        # the offending field is named


def test_patch_unknown_id_404(client, tmp_db):
    resp = client.patch("/api/applications/999999",
                        json={"notes": "x"}, headers=_H)
    assert resp.status_code == 404


def test_patch_headerless_403(client, tmp_db):
    a = _add(company="Acme")
    resp = client.patch(f"/api/applications/{a}", json={"notes": "x"})
    assert resp.status_code == 403
    assert service.get_job(a)["notes"] == ""    # nothing mutated


# ── status ────────────────────────────────────────────────────────────────────

def test_status_happy_path_stamps_applied(client, tmp_db):
    a = _add(company="Acme")
    resp = client.post(f"/api/applications/{a}/status",
                       json={"status": "applied"}, headers=_H)
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["job"]["status"] == "applied"
    # set_status auto-stamps date_applied on entering 'applied'.
    assert body["job"]["date_applied"]


def test_status_invalid_400(client, tmp_db):
    a = _add(company="Acme")
    resp = client.post(f"/api/applications/{a}/status",
                       json={"status": "banana"}, headers=_H)
    assert resp.status_code == 400
    assert resp.get_json()["ok"] is False
    assert service.get_job(a)["status"] == "interested"  # unchanged


def test_status_unknown_id_404(client, tmp_db):
    resp = client.post("/api/applications/999999/status",
                       json={"status": "applied"}, headers=_H)
    assert resp.status_code == 404


def test_status_headerless_403(client, tmp_db):
    a = _add(company="Acme")
    resp = client.post(f"/api/applications/{a}/status", json={"status": "applied"})
    assert resp.status_code == 403
    assert service.get_job(a)["status"] == "interested"


# ── archive / restore / delete ────────────────────────────────────────────────

def test_archive_and_restore(client, tmp_db):
    a = _add(company="Acme")
    assert client.post(f"/api/applications/{a}/archive", headers=_H).status_code == 200
    assert db.get_counts()["archived"] == 1
    assert client.post(f"/api/applications/{a}/restore", headers=_H).status_code == 200
    assert db.get_counts()["archived"] == 0


def test_archive_unknown_id_404(client, tmp_db):
    assert client.post("/api/applications/999999/archive",
                       headers=_H).status_code == 404


def test_archive_headerless_403(client, tmp_db):
    a = _add(company="Acme")
    resp = client.post(f"/api/applications/{a}/archive")
    assert resp.status_code == 403
    assert db.get_counts()["archived"] == 0


def test_restore_headerless_403(client, tmp_db):
    a = _add(company="Acme")
    service.archive_job(a)
    resp = client.post(f"/api/applications/{a}/restore")
    assert resp.status_code == 403
    assert db.get_counts()["archived"] == 1


def test_delete_happy_path(client, tmp_db):
    a = _add(company="Acme")
    resp = client.delete(f"/api/applications/{a}", headers=_H)
    assert resp.status_code == 200
    assert service.get_job(a) is None


def test_delete_unknown_id_404(client, tmp_db):
    assert client.delete("/api/applications/999999", headers=_H).status_code == 404


def test_delete_headerless_403(client, tmp_db):
    a = _add(company="Acme")
    resp = client.delete(f"/api/applications/{a}")
    assert resp.status_code == 403
    assert service.get_job(a) is not None       # still there


# ── notes -> timeline ─────────────────────────────────────────────────────────

def test_note_appends_timeline(client, tmp_db):
    a = _add(company="Acme")
    resp = client.post(f"/api/applications/{a}/notes",
                       json={"note": "left a voicemail"}, headers=_H)
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert len(body["timeline"]) == 1
    entry = body["timeline"][0]
    assert entry["kind"] == "note"
    assert entry["note"] == "left a voicemail"


def test_note_blank_400(client, tmp_db):
    a = _add(company="Acme")
    resp = client.post(f"/api/applications/{a}/notes",
                       json={"note": "   "}, headers=_H)
    assert resp.status_code == 400
    assert service.status_timeline(a) == []


def test_note_unknown_id_404(client, tmp_db):
    resp = client.post("/api/applications/999999/notes",
                       json={"note": "x"}, headers=_H)
    assert resp.status_code == 404


def test_note_headerless_403(client, tmp_db):
    a = _add(company="Acme")
    resp = client.post(f"/api/applications/{a}/notes", json={"note": "x"})
    assert resp.status_code == 403
    assert service.status_timeline(a) == []


# ── interview rounds (sub-CRUD) ───────────────────────────────────────────────

def test_round_add_list_update_delete(client, tmp_db):
    a = _add(company="Acme")
    # add
    resp = client.post(f"/api/applications/{a}/rounds",
                       json={"kind": "phone", "scheduled_at": "2026-07-10T14:00",
                             "interviewer": "Pat"}, headers=_H)
    assert resp.status_code == 201
    body = resp.get_json()
    rid = body["id"]
    assert isinstance(rid, int)
    assert len(body["rounds"]) == 1
    # a 'phone' round advances a pre-interview app to phone_screen (engine coherence)
    assert service.get_job(a)["status"] == "phone_screen"
    # update
    up = client.patch(f"/api/applications/{a}/rounds/{rid}",
                      json={"outcome": "passed"}, headers=_H)
    assert up.status_code == 200
    assert up.get_json()["rounds"][0]["outcome"] == "passed"
    # delete
    dele = client.delete(f"/api/applications/{a}/rounds/{rid}", headers=_H)
    assert dele.status_code == 200
    assert dele.get_json()["rounds"] == []


def test_round_add_unknown_app_404(client, tmp_db):
    resp = client.post("/api/applications/999999/rounds",
                       json={"kind": "phone"}, headers=_H)
    assert resp.status_code == 404


def test_round_update_unknown_field_400(client, tmp_db):
    a = _add(company="Acme")
    rid = service.add_interview_round(a, kind="phone", scheduled_at="2026-07-10")
    resp = client.patch(f"/api/applications/{a}/rounds/{rid}",
                        json={"bogus": "x"}, headers=_H)
    assert resp.status_code == 400
    assert "bogus" in resp.get_json()["error"]


def test_round_update_wrong_app_404(client, tmp_db):
    a = _add(company="Acme")
    b = _add(title="QA", company="Globex")
    rid = service.add_interview_round(a, kind="phone", scheduled_at="2026-07-10")
    # round rid belongs to app a, not b -> 404 under b's path
    resp = client.patch(f"/api/applications/{b}/rounds/{rid}",
                        json={"outcome": "x"}, headers=_H)
    assert resp.status_code == 404


def test_round_add_headerless_403(client, tmp_db):
    a = _add(company="Acme")
    resp = client.post(f"/api/applications/{a}/rounds", json={"kind": "phone"})
    assert resp.status_code == 403
    assert service.list_interview_rounds(a) == []


def test_round_update_headerless_403(client, tmp_db):
    a = _add(company="Acme")
    rid = service.add_interview_round(a, kind="phone", scheduled_at="2026-07-10")
    resp = client.patch(f"/api/applications/{a}/rounds/{rid}",
                        json={"outcome": "passed"})
    assert resp.status_code == 403


def test_round_delete_headerless_403(client, tmp_db):
    a = _add(company="Acme")
    rid = service.add_interview_round(a, kind="phone", scheduled_at="2026-07-10")
    resp = client.delete(f"/api/applications/{a}/rounds/{rid}")
    assert resp.status_code == 403
    assert len(service.list_interview_rounds(a)) == 1


# ── .ics download ─────────────────────────────────────────────────────────────

def test_round_ics_download(client, tmp_db):
    a = _add(company="Acme")
    rid = service.add_interview_round(a, kind="onsite",
                                      scheduled_at="2026-07-10T14:00",
                                      interviewer="Pat")
    resp = client.get(f"/api/applications/{a}/rounds/{rid}/ics")
    assert resp.status_code == 200
    # Attachment header + calendar mimetype.
    assert resp.headers["Content-Type"].startswith("text/calendar")
    assert "attachment" in resp.headers["Content-Disposition"]
    assert ".ics" in resp.headers["Content-Disposition"]
    text = resp.get_data(as_text=True)
    assert "BEGIN:VEVENT" in text
    assert "END:VEVENT" in text
    assert "SUMMARY:" in text


def test_round_ics_no_schedule_400(client, tmp_db):
    a = _add(company="Acme")
    rid = service.add_interview_round(a, kind="onsite")  # no scheduled_at
    resp = client.get(f"/api/applications/{a}/rounds/{rid}/ics")
    assert resp.status_code == 400
    assert resp.get_json()["ok"] is False


def test_round_ics_unknown_round_404(client, tmp_db):
    a = _add(company="Acme")
    resp = client.get(f"/api/applications/{a}/rounds/999999/ics")
    assert resp.status_code == 404


def test_round_ics_unknown_app_404(client, tmp_db):
    resp = client.get("/api/applications/999999/rounds/1/ics")
    assert resp.status_code == 404
