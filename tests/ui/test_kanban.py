"""SB-5 — visual Kanban board over the tracker DB. Pure layout/logic helpers are
tested without a display; the widget build + a service-backed move are tested
headlessly (skipped when no display), mirroring tests/ui/test_cycle_dialogs.py.
"""
import tkinter as tk

import pytest

from ui import kanban
from tracker import db


# ── Pure helpers (no display) ─────────────────────────────────────────────────

def test_columns_are_the_named_funnel_stages():
    # The eight stages the plan names, in funnel order, plus withdrawn so no
    # tracked row is ever invisible. Every column is a real tracker status.
    for named in ("interested", "applied", "phone_screen", "interview", "offer",
                  "accepted", "rejected", "ghosted"):
        assert named in kanban.COLUMNS
    assert set(kanban.COLUMNS) <= set(db.STATUSES)
    # Funnel order: interested precedes applied precedes interview precedes offer.
    idx = kanban.COLUMNS.index
    assert idx("interested") < idx("applied") < idx("interview") < idx("offer")


def test_forward_targets_never_downgrade_and_terminal_is_readonly():
    # A progression stage advances to the next step + outcomes, never backwards.
    assert kanban.forward_targets("applied")[0] == "phone_screen"
    assert "interested" not in kanban.forward_targets("applied")
    assert "applied" not in kanban.forward_targets("interview")
    # Terminal/outcome columns offer no advance (read-only on the board).
    for term in ("accepted", "rejected", "withdrawn", "ghosted"):
        assert kanban.forward_targets(term) == []
    # A card never lists its own status as a move target.
    for s in ("interested", "applied", "phone_screen", "interview", "offer"):
        assert s not in kanban.forward_targets(s)


def test_forward_targets_offer_can_reach_outcomes():
    t = kanban.forward_targets("offer")
    assert "accepted" in t and "rejected" in t
    assert "interested" not in t and "applied" not in t


def test_days_in_stage_uses_applied_then_added():
    # An applied row clocks from date_applied.
    assert kanban.days_in_stage(
        {"status": "applied", "date_applied": "2026-07-01",
         "date_added": "2026-06-01"}, today="2026-07-02") == 1
    # An interested row (never applied) clocks from date_added.
    assert kanban.days_in_stage(
        {"status": "interested", "date_added": "2026-06-25"},
        today="2026-07-02") == 7
    # No usable date -> None (not a crash, not a bogus 0).
    assert kanban.days_in_stage({"status": "applied"}, today="2026-07-02") is None
    # A future reference date clamps to 0, never negative.
    assert kanban.days_in_stage(
        {"status": "applied", "date_applied": "2026-07-10"},
        today="2026-07-02") == 0


def test_days_in_stage_prefers_entered_at_over_applied_date():
    # The "days here" clock must measure time IN THE CURRENT STAGE, not time
    # since applying. A card applied 30 days ago that moved to 'interview'
    # yesterday reads "1 day here" — the entered_at timestamp wins.
    row = {"status": "interview", "date_applied": "2026-06-02",
           "date_added": "2026-06-01"}
    assert kanban.days_in_stage(row, today="2026-07-02",
                                entered_at="2026-07-01") == 1
    # Without an entered_at (no transition history), it falls back to the
    # applied/added heuristic (unchanged legacy behavior).
    assert kanban.days_in_stage(row, today="2026-07-02") == 30
    # A blank/whitespace entered_at is treated as "no timestamp" -> fallback.
    assert kanban.days_in_stage(row, today="2026-07-02", entered_at="  ") == 30


def test_days_label_wording():
    assert kanban.days_label(0) == "today"
    assert kanban.days_label(1) == "1 day"
    assert kanban.days_label(9) == "9 days"
    assert kanban.days_label(None) == ""


def test_group_by_status_buckets_and_drops_unknown():
    rows = [{"status": "applied", "id": 1}, {"status": "offer", "id": 2},
            {"status": "applied", "id": 3}, {"status": "archived_x", "id": 9}]
    g = kanban.group_by_status(rows)
    # every column key present
    assert set(g.keys()) == set(kanban.COLUMNS)
    assert [r["id"] for r in g["applied"]] == [1, 3]
    assert [r["id"] for r in g["offer"]] == [2]
    # unknown status is not on the board anywhere
    all_ids = [r["id"] for v in g.values() for r in v]
    assert 9 not in all_ids


# ── entered_status_at over a real two-transition history (no display) ─────────

def test_entered_status_at_uses_latest_transition_into_current_status(
        tmp_path, monkeypatch):
    # A card that moves applied -> phone_screen -> interview records a
    # status_history row per transition; entered_status_at must return the
    # timestamp of the transition INTO the current status (interview), not the
    # older applied one.
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "tracker.db")
    db.init_db()
    from tracker import service as svc
    jid = db.add_job("Controls Engineer", "Acme", status="applied",
                     date_applied="2026-06-01")
    svc.set_status(jid, "phone_screen")
    svc.set_status(jid, "interview")
    ts = svc.entered_status_at(jid)          # current status == interview
    assert ts is not None
    tl = svc.status_timeline(jid)
    interview_events = [e for e in tl
                        if e["new_status"] == "interview" and e["kind"] == "status"]
    assert ts == interview_events[-1]["changed_at"]
    # A note added at the current status (old==new) must NOT reset the clock.
    svc.add_status_note(jid, "recruiter emailed")
    assert svc.entered_status_at(jid) == ts
    # A row created directly at a status and never moved has no transition into
    # it -> None (so the badge falls back to the row's own dates).
    jid2 = db.add_job("RN", "Mercy", status="interested")
    assert svc.entered_status_at(jid2) is None


# ── Headless widget build + a real move through the service ───────────────────

@pytest.fixture
def root(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "tracker.db")
    db.init_db()
    try:
        r = tk.Tk()
    except tk.TclError:
        pytest.skip("no display")
    import gui
    gui.theme.apply_theme(r)
    yield r
    try:
        r.destroy()
    except tk.TclError:
        pass


def test_board_builds_columns_and_cards(root):
    db.add_job("Controls Engineer", "Acme", status="applied",
               date_applied="2026-07-01")
    db.add_job("RN", "Mercy", status="interested")
    tab = kanban.KanbanTab(root)
    root.update_idletasks()
    # The board frame has one child frame per column.
    cols = tab._board.winfo_children()
    assert len(cols) == len(kanban.COLUMNS)
    assert tab.winfo_exists()


def test_board_move_advances_through_the_service(root):
    jid = db.add_job("Controls Engineer", "Acme", status="applied",
                     date_applied="2026-07-01")
    tab = kanban.KanbanTab(root)
    # Move advances via the SAME service verb the Tracker uses; the row's status
    # changes and a status_history transition is recorded (Wave-1 coherence).
    tab._move(jid, "phone_screen")
    assert db.get_job(jid)["status"] == "phone_screen"
    # The board re-read itself and still stands.
    assert tab.winfo_exists()


def test_board_edit_opens_jobdialog_and_saves(root):
    import gui
    jid = db.add_job("Controls Engineer", "Acme", status="interested")
    tab = kanban.KanbanTab(root)
    # Intercept the modal so _edit doesn't block, and feed a result.
    orig_wait = gui.JobDialog.wait_window
    gui.JobDialog.wait_window = lambda self, *a, **k: None
    try:
        # Drive _edit; the dialog builds, we set a result + destroy, then the tab
        # persists it through the service.
        captured = {}
        orig_init = gui.JobDialog.__init__

        def patched_init(self, parent, job=None):
            orig_init(self, parent, job=job)
            self.result = {"title": "Controls Engineer II", "company": "Acme",
                           "location": "", "salary_text": "", "url": "",
                           "status": "applied", "date_applied": "", "notes": "",
                           "follow_up_date": "", "deadline": "", "contact": "",
                           "offer_amount": "", "offer_deadline": "",
                           "offer_notes": ""}
            captured["built"] = True

        gui.JobDialog.__init__ = patched_init
        try:
            tab._edit(jid)
        finally:
            gui.JobDialog.__init__ = orig_init
        assert captured.get("built")
        row = db.get_job(jid)
        assert row["title"] == "Controls Engineer II"
        assert row["status"] == "applied"
    finally:
        gui.JobDialog.wait_window = orig_wait
