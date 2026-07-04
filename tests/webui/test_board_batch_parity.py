"""Parity test for board.py's batched entered_status_at replacement.

The board used to call ``service.entered_status_at(job_id, status)`` once PER
CARD (one connection+query each — an N+1). ``_entered_status_at_batch`` replaces
that with a single grouped query over all card ids at once; this test seeds
several jobs with multiple status transitions each (including same-status
self-transitions / notes, which the WHERE clause must still exclude) and asserts
the batched lookup agrees with ``db.entered_status_at`` for every (job, status)
pair, card by card.
"""
from tracker import db, service
from webui.api.board import _entered_status_at_batch


def _add(title="Job", company="Acme", **extra) -> int:
    return service.add_manual_job(title=title, company=company, **extra)


def test_batched_lookup_matches_entered_status_at_per_card(client, tmp_db):
    a = _add(title="A", company="Acme")
    b = _add(title="B", company="Globex")
    c = _add(title="C", company="Initech")  # never moves — stays 'interested'

    # Multiple genuine transitions for `a` (interested -> applied -> phone_screen),
    # plus a same-status note (must NOT reset/duplicate the 'applied' clock).
    service.set_status(a, "applied")
    db.add_status_note(a, "followed up")  # old_status == new_status == 'applied'
    service.set_status(a, "phone_screen")

    # `b` moves once.
    service.set_status(b, "applied")

    # `c` never transitions — entered_status_at should read None for every status.

    all_ids = [a, b, c]
    batch = _entered_status_at_batch(all_ids)

    for jid in all_ids:
        for status in db.STATUSES:
            expected = db.entered_status_at(jid, status)
            actual = batch.get((jid, status))
            assert actual == expected, (jid, status, expected, actual)


def test_batched_lookup_empty_ids_returns_empty(client, tmp_db):
    assert _entered_status_at_batch([]) == {}


def test_batched_lookup_no_status_history_table(client, tmp_db):
    """A DB with no status_history table (matches entered_status_at's own guard)
    returns {} rather than raising."""
    with db.get_conn() as conn:
        conn.execute("DROP TABLE IF EXISTS status_history")
        conn.commit()
    a = _add(title="A", company="Acme")
    assert _entered_status_at_batch([a]) == {}
    # And the real per-row helper agrees (None, not a raise).
    assert db.entered_status_at(a, "interested") is None


def test_board_route_end_to_end_days_in_stage_matches_direct_call(client, tmp_db):
    """End-to-end: the /api/board route (which now uses the batched helper) reports
    the same days_in_stage a direct entered_status_at call would produce."""
    from ui import kanban_core

    a = _add(title="A", company="Acme")
    service.set_status(a, "applied")
    body = client.get("/api/board").get_json()
    by_status = {c["status"]: c for c in body["columns"]}
    card = by_status["applied"]["cards"][0]

    row = service.get_job(a)
    entered_at = db.entered_status_at(a, "applied")
    expected_days = kanban_core.days_in_stage(row, entered_at=entered_at)
    assert card["days_in_stage"] == expected_days
