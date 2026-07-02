"""D1 — full application-cycle tracking (P5).

Covers: centralized entered-'applied' side-effects in db.update_job across all
entry paths; the accepted/ghosted terminal states in the enum + funnel + terminal
set; the auto-ghost 'no response' query; interview-round CRUD + .ics content;
offer-field migration; note-only status_history events + timeline; contacts
surfacing at the service level; the due-badge counting; PRAGMA quick_check +
rolling backup; the applications CSV export; and the by_source interview_rate
rename. Temp-db fixtures throughout; no network, no tkinter.
"""
import csv
from datetime import date, timedelta

import pytest

import tracker.db as db
from tracker import service as svc
from tracker import analytics


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "tracker.db")
    db.init_db()
    return db.DB_PATH


# ── 1. Centralized entered-'applied' side-effects (all entry paths) ───────────

def test_update_job_stamps_date_applied_and_follow_up_on_applied(tmp_db):
    """Setting status->applied via update_job stamps date_applied (if blank) and
    a +7-day follow_up_date (if blank) — the Apply Queue path."""
    jid = db.add_job("Nurse", "Mercy", status="interested")
    db.update_job(jid, status="applied")
    j = db.get_job(jid)
    assert j["date_applied"] == date.today().isoformat()
    assert j["follow_up_date"] == (date.today() + timedelta(days=7)).isoformat()


def test_update_job_applied_inherited_by_set_status_quick_status(tmp_db):
    """Tracker quick-status (service.set_status) inherits the same side-effects."""
    jid = db.add_job("Welder", "Steelco", status="interested")
    svc.set_status(jid, "applied")
    j = db.get_job(jid)
    assert j["date_applied"] == date.today().isoformat()
    assert j["follow_up_date"]


def test_update_job_applied_does_not_overwrite_existing(tmp_db):
    """A pre-existing date_applied / follow_up_date is left untouched."""
    jid = db.add_job("Teacher", "District 9", status="interested",
                     date_applied="2026-01-01", follow_up_date="2026-02-02")
    db.update_job(jid, status="applied")
    j = db.get_job(jid)
    assert j["date_applied"] == "2026-01-01"
    assert j["follow_up_date"] == "2026-02-02"


def test_update_job_caller_supplied_values_win(tmp_db):
    """When the caller passes date_applied/follow_up_date explicitly, they win
    over the auto-stamp."""
    jid = db.add_job("Driver", "Hauler", status="interested")
    db.update_job(jid, status="applied", date_applied="2026-03-03",
                  follow_up_date="2026-03-10")
    j = db.get_job(jid)
    assert j["date_applied"] == "2026-03-03"
    assert j["follow_up_date"] == "2026-03-10"


def test_flask_update_path_arms_follow_up(tmp_db, monkeypatch):
    """The Flask /update route calls db.update_job, so it inherits the stamp."""
    from tracker import app as flask_app
    jid = db.add_job("Analyst", "Bank", status="interested")
    # /update ultimately calls tracker.db.update_job (imported into tracker.app).
    flask_app.update_job(jid, status="applied")
    j = db.get_job(jid)
    assert j["date_applied"] == date.today().isoformat()
    assert j["follow_up_date"]


# ── 2. accepted / ghosted terminal states ─────────────────────────────────────

def test_accepted_and_ghosted_in_enum():
    assert "accepted" in db.STATUSES
    assert "ghosted" in db.STATUSES
    assert db.STATUS_LABELS["accepted"] == "Accepted"
    assert db.STATUS_LABELS["ghosted"] == "Ghosted"


def test_funnel_has_accepted_stage_and_terminal_set():
    assert analytics.FUNNEL[-1] == "accepted"
    assert analytics.TERMINAL == {"rejected", "withdrawn", "ghosted"}


def test_offer_to_accepted_conversion_reportable(tmp_db):
    """A job that moved offer->accepted registers an offer->accepted conversion."""
    jid = db.add_job("SRE", "Cloudy", status="interested")
    for s in ("applied", "phone_screen", "interview", "offer", "accepted"):
        db.update_job(jid, status=s)
    with db.get_conn() as conn:
        f = analytics.funnel(conn)
    conv = {(c["from"], c["to"]): c["rate"] for c in f["conversions"]}
    assert conv[("offer", "accepted")] == 1.0
    stages = {s["stage"]: s["count"] for s in f["stage_counts"]}
    assert stages["accepted"] == 1


# ── 3. Auto-ghost 'no response' query ─────────────────────────────────────────

def test_stale_applications_flags_silent_applied(tmp_db):
    """An 'applied' job whose last history is older than the window is flagged;
    a recently-moved one is not."""
    old = db.add_job("QA", "Old Co", status="interested")
    db.update_job(old, status="applied")  # transition logged as of now
    # Backdate its only history row well past the 21-day window.
    with db.get_conn() as conn:
        conn.execute(
            "UPDATE status_history SET changed_at=? WHERE job_id=?",
            ((date.today() - timedelta(days=40)).isoformat() + "T00:00:00+00:00",
             old))
        conn.commit()
    fresh = db.add_job("QA2", "New Co", status="interested")
    db.update_job(fresh, status="applied")  # moved just now -> not stale

    stale = db.stale_applications()
    ids = {r["id"] for r in stale}
    assert old in ids
    assert fresh not in ids
    row = next(r for r in stale if r["id"] == old)
    assert row["due_kind"] == "no response"


def test_stale_applications_ignores_non_applied(tmp_db):
    jid = db.add_job("Old Interview", "Co", status="interested")
    db.update_job(jid, status="applied")
    db.update_job(jid, status="interview")
    with db.get_conn() as conn:
        conn.execute(
            "UPDATE status_history SET changed_at=? WHERE job_id=?",
            ((date.today() - timedelta(days=60)).isoformat() + "T00:00:00+00:00",
             jid))
        conn.commit()
    assert all(r["id"] != jid for r in db.stale_applications())


# ── 4. Interview rounds CRUD + .ics content ───────────────────────────────────

def test_interview_round_crud(tmp_db):
    jid = db.add_job("Eng", "Acme", status="interested")
    r1 = db.add_interview_round(jid, kind="phone", scheduled_at="2026-08-01",
                                interviewer="Pat")
    r2 = db.add_interview_round(jid, kind="tech")
    rounds = db.list_interview_rounds(jid)
    assert [r["round_no"] for r in rounds] == [1, 2]
    assert rounds[0]["kind"] == "phone"
    db.update_interview_round(r1, outcome="passed", interviewer="Pat Smith")
    assert db.get_interview_round(r1)["outcome"] == "passed"
    db.delete_interview_round(r2)
    assert [r["id"] for r in db.list_interview_rounds(jid)] == [r1]


def test_round_ics_parses_back(tmp_db, tmp_path):
    jid = db.add_job("Eng", "Acme Corp", status="interview",
                     url="https://jobs.example/eng")
    rid = db.add_interview_round(jid, kind="onsite",
                                 scheduled_at="2026-08-15T14:30:00",
                                 interviewer="Dana", notes="Bring; a, laptop")
    app = db.get_job(jid)
    rnd = db.get_interview_round(rid)
    ics = svc.round_to_ics(app, rnd)
    # Parse the VEVENT back out.
    lines = ics.replace("\r\n", "\n").splitlines()
    assert "BEGIN:VEVENT" in lines and "END:VEVENT" in lines
    fields = {}
    for ln in lines:
        if ":" in ln:
            k, v = ln.split(":", 1)
            fields[k.split(";")[0]] = v
    assert fields["DTSTART"] == "20260815T143000"
    assert fields["DTEND"] == "20260815T153000"
    assert "onsite".title() in fields["SUMMARY"]
    assert "Acme Corp" in fields["SUMMARY"]
    # TEXT escaping: the comma+semicolon in notes must be backslash-escaped.
    assert "\\," in fields["DESCRIPTION"] and "\\;" in fields["DESCRIPTION"]


def test_write_round_ics_creates_file(tmp_db, tmp_path):
    jid = db.add_job("Eng", "Beta", status="interview")
    rid = db.add_interview_round(jid, kind="final", scheduled_at="2026-09-01")
    path = svc.write_round_ics(db.get_job(jid), db.get_interview_round(rid),
                               tmp_path / "out")
    assert path.exists()
    assert path.suffix == ".ics"
    assert "BEGIN:VCALENDAR" in path.read_text(encoding="utf-8")


def test_round_ics_without_schedule_raises(tmp_db):
    jid = db.add_job("Eng", "Gamma", status="interview")
    rid = db.add_interview_round(jid, kind="phone")  # no scheduled_at
    with pytest.raises(ValueError):
        svc.round_to_ics(db.get_job(jid), db.get_interview_round(rid))


# ── 5. Offer fields migration ─────────────────────────────────────────────────

def test_offer_fields_exist_and_editable(tmp_db):
    with db.get_conn() as conn:
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(applications)")}
    assert {"offer_amount", "offer_deadline", "offer_notes"} <= cols
    jid = db.add_job("Eng", "Acme", status="offer")
    db.update_job(jid, offer_amount="$120k", offer_deadline="2026-08-30",
                  offer_notes="verbal, negotiating")
    j = db.get_job(jid)
    assert j["offer_amount"] == "$120k"
    assert j["offer_deadline"] == "2026-08-30"
    assert j["offer_notes"] == "verbal, negotiating"


def test_offer_fields_migrate_in_place(tmp_path, monkeypatch):
    """A pre-v7 DB (no offer_* columns) upgrades in place without data loss."""
    import sqlite3
    p = tmp_path / "old.db"
    conn = sqlite3.connect(str(p))
    conn.execute(
        "CREATE TABLE applications (id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "title TEXT NOT NULL, company TEXT NOT NULL, url TEXT DEFAULT '', "
        "status TEXT, date_added TEXT NOT NULL, date_applied TEXT DEFAULT '', "
        "notes TEXT)")
    conn.execute("INSERT INTO applications (title, company, status, date_added) "
                 "VALUES ('X','Y','offer','2026-01-01')")
    conn.execute("PRAGMA user_version = 1")
    conn.commit()
    conn.close()
    monkeypatch.setattr(db, "DB_PATH", p)
    assert db.init_db() is True  # migration ran
    with db.get_conn() as conn:
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(applications)")}
    assert {"offer_amount", "offer_deadline", "offer_notes"} <= cols
    assert db.get_job(1)["company"] == "Y"  # data survived


# ── 6. Note-only history events + timeline ────────────────────────────────────

def test_add_status_note_creates_note_only_event(tmp_db):
    jid = db.add_job("Eng", "Acme", status="applied")
    hid = db.add_status_note(jid, "Recruiter said 2 weeks")
    assert hid is not None
    with db.get_conn() as conn:
        row = conn.execute(
            "SELECT old_status, new_status, note FROM status_history WHERE id=?",
            (hid,)).fetchone()
    assert row["old_status"] == row["new_status"] == "applied"
    assert row["note"] == "Recruiter said 2 weeks"


def test_add_status_note_blank_is_noop(tmp_db):
    jid = db.add_job("Eng", "Acme", status="applied")
    assert db.add_status_note(jid, "   ") is None


def test_status_timeline_orders_and_classifies(tmp_db):
    jid = db.add_job("Eng", "Acme", status="interested")
    db.update_job(jid, status="applied")
    db.add_status_note(jid, "left voicemail")
    db.update_job(jid, status="phone_screen")
    tl = db.status_timeline(jid)
    kinds = [e["kind"] for e in tl]
    assert kinds == ["status", "note", "status"]
    assert tl[1]["note"] == "left voicemail"
    assert tl[2]["new_status"] == "phone_screen"


# ── 7. Contacts surfacing (service level) ─────────────────────────────────────

def test_referral_hint(tmp_db):
    assert svc.referral_hint("Acme") == ""
    db.add_contact("Jane Doe", company="Acme")
    db.add_contact("John Roe", company="acme")  # case-insensitive
    hint = svc.referral_hint("Acme")
    assert "2 people at Acme" in hint
    assert "Jane Doe" in hint and "John Roe" in hint
    assert "referral" in hint


def test_referral_hint_singular(tmp_db):
    db.add_contact("Solo", company="Beta")
    assert "1 person at Beta" in svc.referral_hint("Beta")


def test_contact_with_app_id_and_last_contacted(tmp_db):
    jid = db.add_job("Eng", "Acme", status="interested")
    cid = svc.add_contact("Ref Erral", company="Acme", app_id=jid,
                          last_contacted="2026-07-01")
    c = next(c for c in db.list_contacts() if c["id"] == cid)
    assert c["app_id"] == jid
    assert c["last_contacted"] == "2026-07-01"


# ── 8. Due badge counting ─────────────────────────────────────────────────────

def test_count_followups_due_includes_no_response(tmp_db):
    # A due follow-up.
    a = db.add_job("A", "Co", status="applied",
                   follow_up_date=(date.today() - timedelta(days=1)).isoformat())
    # A silent applied job (no-response) with NO due follow-up.
    b = db.add_job("B", "Co2", status="interested")
    db.update_job(b, status="applied")  # real transition -> a history row to age
    with db.get_conn() as conn:
        conn.execute(
            "UPDATE status_history SET changed_at=? WHERE job_id=?",
            ((date.today() - timedelta(days=40)).isoformat() + "T00:00:00+00:00", b))
        # b was auto-stamped a +7d follow-up by update_job; clear it so it counts
        # only via the no-response path.
        conn.execute("UPDATE applications SET follow_up_date='' WHERE id=?", (b,))
        conn.commit()
    n_with = db.count_followups_due(include_no_response=True)
    n_without = db.count_followups_due(include_no_response=False)
    assert n_without == 1        # only the due follow-up
    assert n_with == 2           # + the no-response nudge


def test_count_followups_due_no_double_count(tmp_db):
    """A silent applied job that ALSO has a due follow-up is counted once."""
    jid = db.add_job("A", "Co", status="interested")
    db.update_job(jid, status="applied")
    with db.get_conn() as conn:
        conn.execute(
            "UPDATE status_history SET changed_at=? WHERE job_id=?",
            ((date.today() - timedelta(days=40)).isoformat() + "T00:00:00+00:00", jid))
        conn.execute(
            "UPDATE applications SET follow_up_date=? WHERE id=?",
            ((date.today() - timedelta(days=1)).isoformat(), jid))
        conn.commit()
    # There IS one due follow-up AND it's stale — must count as 1, not 2.
    assert db.count_followups_due(include_no_response=True) == 1


# ── 9. Data safety: quick_check + rolling backup + CSV export ─────────────────

def test_quick_check_ok(tmp_db):
    ok, msg = db.quick_check()
    assert ok is True
    assert msg == "ok"


def test_quick_check_missing_db_is_ok(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "nope.db")
    ok, msg = db.quick_check()
    assert ok is True  # nothing to check, not a failure
    assert not (tmp_path / "nope.db").exists()


def test_rolling_backup_writes_and_rotates(tmp_db, tmp_path):
    db.add_job("Eng", "Acme")
    # 8 days of backups; keep=7 should leave the newest 7.
    made = []
    for i in range(8):
        d = (date(2026, 7, 1) + timedelta(days=i)).isoformat()
        p = db.rolling_backup(keep=7, today=d)
        assert p is not None
        made.append(p)
    # Second call for the same day is a no-op.
    assert db.rolling_backup(keep=7, today="2026-07-08") is None
    snaps = sorted(tmp_path.glob("tracker.db.bak-2026-*"))
    assert len(snaps) == 7  # oldest (07-01) pruned
    assert not (tmp_path / "tracker.db.bak-2026-07-01").exists()
    assert (tmp_path / "tracker.db.bak-2026-07-08").exists()


def test_rolling_backup_keeps_migration_backups(tmp_db, tmp_path):
    """The dated-backup rotation must not delete '.bak-vN' migration backups."""
    (tmp_path / "tracker.db.bak-v3").write_text("x")
    db.rolling_backup(keep=1, today="2026-07-09")
    assert (tmp_path / "tracker.db.bak-v3").exists()


def test_export_applications_csv_golden(tmp_db, tmp_path):
    jid = db.add_job("Nurse", "Mercy", location="Cincinnati", status="interested",
                     source="careeronestop", salary_text="$40/hr")
    db.update_job(jid, status="applied")
    db.add_status_note(jid, "called back")
    out = tmp_path / "apps.csv"
    n = db.export_applications_csv(out)
    assert n == 1
    with open(out, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 1
    r = rows[0]
    assert r["title"] == "Nurse"
    assert r["company"] == "Mercy"
    assert r["status"] == "applied"
    assert r["source"] == "careeronestop"
    # The full timeline is folded into 'history': the transition + the note.
    assert "interested->applied" in r["history"]
    # S32/L6: a same-status note renders as a note, not a phantom self-transition.
    assert "applied->applied" not in r["history"]
    assert "[note: called back]" in r["history"]


def test_export_csv_excludes_archived(tmp_db, tmp_path):
    keep = db.add_job("Keep", "Co", status="interested")
    gone = db.add_job("Gone", "Co", status="interested")
    db.archive_job(gone)
    out = tmp_path / "apps.csv"
    assert db.export_applications_csv(out) == 1
    with open(out, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert [r["title"] for r in rows] == ["Keep"]
