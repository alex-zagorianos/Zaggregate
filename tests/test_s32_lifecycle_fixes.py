"""S32 tracking-lifecycle correctness fixes (review-lifecycle L3/L4/L6/L7).

- P0-7/L3: update_job / update_interview_round REJECT unknown field names loudly
  (was: silent data loss — 'offer_salary' dropped for the real 'offer_amount').
- L4: adding an interview round advances a pre-interview status so follow-up
  nudging (which keys off status) stays coherent with the round.
- L6: add_status_note self-transitions render as a NOTE in the CSV export, not a
  phantom 'accepted->accepted'.
- L7: applog.warn_once dedups repeated skip/verify warnings to once per run.
"""
import csv
import json

import pytest

import tracker.db as db


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "tracker.db")
    db.init_db()
    return db.DB_PATH


# ── P0-7 / L3: unknown-field guard ────────────────────────────────────────────

def test_update_job_unknown_field_raises(tmp_db):
    jid = db.add_job("Eng", "Acme", status="offer")
    with pytest.raises(db.UnknownFieldError):
        db.update_job(jid, offer_salary="53669")   # real column is offer_amount
    # The wrong-column write must NOT have partially applied.
    assert db.get_job(jid)["offer_amount"] == ""


def test_update_job_unknown_field_is_valueerror_subclass(tmp_db):
    """Existing `except ValueError` handlers still catch it."""
    jid = db.add_job("Eng", "Acme")
    with pytest.raises(ValueError):
        db.update_job(jid, not_a_column="x")


def test_update_job_known_field_still_applies(tmp_db):
    jid = db.add_job("Eng", "Acme", status="offer")
    db.update_job(jid, offer_amount="53669")
    assert db.get_job(jid)["offer_amount"] == "53669"


def test_update_job_empty_call_is_noop_not_error(tmp_db):
    """No fields at all is 'nothing to update', not an unknown-field error."""
    jid = db.add_job("Eng", "Acme")
    db.update_job(jid)  # must not raise


def test_update_job_mixed_known_and_unknown_raises_and_applies_nothing(tmp_db):
    jid = db.add_job("Eng", "Acme")
    with pytest.raises(db.UnknownFieldError):
        db.update_job(jid, status="applied", bogus="x")
    # The whole call is rejected — the known field didn't sneak through.
    assert db.get_job(jid)["status"] == "interested"


def test_update_interview_round_unknown_field_raises(tmp_db):
    jid = db.add_job("Eng", "Acme", status="interview")
    rid = db.add_interview_round(jid, kind="phone")
    with pytest.raises(db.UnknownFieldError):
        db.update_interview_round(rid, outcom="passed")   # typo'd 'outcome'


def test_update_interview_round_known_field_still_applies(tmp_db):
    jid = db.add_job("Eng", "Acme", status="interview")
    rid = db.add_interview_round(jid, kind="phone")
    db.update_interview_round(rid, outcome="passed")
    assert db.get_interview_round(rid)["outcome"] == "passed"


def test_service_update_job_propagates_unknown_field(tmp_db):
    from tracker import service
    jid = db.add_job("Eng", "Acme")
    with pytest.raises(db.UnknownFieldError):
        service.update_job(jid, offer_salary="1")


# ── L4: round advances a pre-interview status ─────────────────────────────────

def test_phone_round_advances_applied_to_phone_screen(tmp_db):
    jid = db.add_job("Nurse", "Acme", status="applied")
    db.add_interview_round(jid, kind="phone")
    assert db.get_job(jid)["status"] == "phone_screen"


def test_non_phone_round_advances_applied_to_interview(tmp_db):
    jid = db.add_job("Eng", "Beta", status="applied")
    db.add_interview_round(jid, kind="tech")
    assert db.get_job(jid)["status"] == "interview"


def test_round_advances_interested_too(tmp_db):
    jid = db.add_job("Eng", "Gamma", status="interested")
    db.add_interview_round(jid, kind="onsite")
    assert db.get_job(jid)["status"] == "interview"


def test_round_never_downgrades_a_later_status(tmp_db):
    """A round logged on an already-advanced app must not revert the funnel."""
    jid = db.add_job("SE", "Delta", status="offer")
    db.add_interview_round(jid, kind="phone")
    assert db.get_job(jid)["status"] == "offer"


def test_round_status_advance_records_history_and_arms_followup_nudge(tmp_db):
    """The advance goes through update_job, so the transition is logged and the
    status now counts toward follow-up nudging (the actual L4 harm)."""
    import datetime
    jid = db.add_job("Nurse", "Acme", status="applied")
    db.add_interview_round(jid, kind="phone")
    # A history row for applied->phone_screen exists.
    tl = db.status_timeline(jid)
    assert any(e["old_status"] == "applied" and e["new_status"] == "phone_screen"
               for e in tl)
    # phone_screen is in the follow-up nudge status set: set an overdue follow-up
    # and confirm it's counted.
    yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    db.update_job(jid, follow_up_date=yesterday)
    assert db.count_followups_due() >= 1


# ── L6: CSV export renders a self-transition note as a note ───────────────────

def test_csv_export_note_is_not_phantom_self_transition(tmp_db, tmp_path):
    jid = db.add_job("X", "Y", status="accepted")
    db.add_status_note(jid, "Signed the offer today")
    out = tmp_path / "export.csv"
    db.export_applications_csv(out)
    with open(out, newline="", encoding="utf-8") as fh:
        row = {r["id"]: r for r in csv.DictReader(fh)}[str(jid)]
    hist = row["history"]
    assert "accepted->accepted" not in hist            # no phantom transition
    assert "note: Signed the offer today" in hist       # rendered as a note


def test_csv_export_real_transition_still_shows_arrow(tmp_db, tmp_path):
    jid = db.add_job("X", "Y", status="applied")
    db.update_job(jid, status="interview")
    out = tmp_path / "export.csv"
    db.export_applications_csv(out)
    with open(out, newline="", encoding="utf-8") as fh:
        row = {r["id"]: r for r in csv.DictReader(fh)}[str(jid)]
    assert "applied->interview" in row["history"]        # real transitions intact


# ── L7: warn-once dedup ───────────────────────────────────────────────────────

def test_warn_once_dedups_within_a_run(capsys):
    import applog
    applog.reset_run_warnings()
    assert applog.warn_once("keyless skip", key="k") is True
    assert applog.warn_once("keyless skip", key="k") is False
    assert applog.warn_once("keyless skip", key="k") is False
    out = capsys.readouterr().out
    assert out.count("keyless skip") == 1               # printed exactly once


def test_warn_once_resets_between_runs(capsys):
    import applog
    applog.reset_run_warnings()
    applog.warn_once("skip", key="k")
    applog.reset_run_warnings()
    assert applog.warn_once("skip", key="k") is True    # warns afresh next run


def test_warn_once_distinct_keys_each_warn_once(capsys):
    import applog
    applog.reset_run_warnings()
    applog.warn_once("[jooble] skip", key="jooble")
    applog.warn_once("[careerjet] skip", key="careerjet")
    applog.warn_once("[jooble] skip", key="jooble")     # dup
    out = capsys.readouterr().out
    assert out.count("[jooble] skip") == 1
    assert out.count("[careerjet] skip") == 1
