"""Kanban board API — Phase 2.

``GET /api/board`` shapes the tracked applications into funnel COLUMNS for the
dnd-kit board, reusing the Tk-free kanban pure helpers (``ui.kanban_core``) so the
web board and the tk board compute the exact same column order, day-in-stage
math, and forward-move targets. Read-only: the drag-drop MOVE goes through
``POST /api/applications/<id>/status`` (the applications module), not here.

Each card is a serialized application row augmented with:
  * ``days_in_stage``   — whole days in the current status (entered_status_at
                          clock, falling back to applied/added), or None.
  * ``days_label``      — the compact 'today' / '1 day' / 'N days' badge.
  * ``forward_targets`` — the non-downgrading statuses the card may move to
                          ([] for a terminal stage).

Columns are emitted in ``kanban_core.COLUMNS`` order (== ``db.STATUSES`` order,
which the tk board's headless test already asserts), each labelled via
``db.STATUS_LABELS``.
"""
from __future__ import annotations

from flask import Blueprint, jsonify

from tracker import db
from tracker import service
from tracker.db import get_conn
from ui import kanban_core
from ..serializers import app_row_list

board_bp = Blueprint("webui_board", __name__)


def _entered_status_at_batch(job_ids: list[int]) -> dict[tuple[int, str], str]:
    """Batched replacement for calling ``service.entered_status_at(job_id, status)``
    once per card. Opens ONE connection and runs a single grouped query instead of
    ``len(job_ids)`` separate connections+queries (the board's former N+1).

    Replicates ``tracker.db.entered_status_at``'s exact semantics: for each
    ``(job_id, new_status)`` pair, the latest ``changed_at`` among genuine
    transitions only (``old_status != new_status`` — a note-only event must NOT
    reset the clock). Returns ``{(job_id, status): changed_at}`` for every pair
    that has at least one such transition; a pair with none is simply absent (the
    caller's ``.get(...)`` -> None mirrors ``entered_status_at``'s None return).

    Empty ``job_ids`` -> ``{}`` without touching the DB (no card, nothing to ask)."""
    if not job_ids:
        return {}
    with get_conn() as conn:
        if not _has_status_history(conn):
            return {}
        placeholders = ",".join("?" for _ in job_ids)
        rows = conn.execute(
            f"SELECT job_id, new_status, MAX(changed_at) AS entered_at "
            f"FROM status_history "
            f"WHERE old_status != new_status AND job_id IN ({placeholders}) "
            f"GROUP BY job_id, new_status",
            list(job_ids),
        ).fetchall()
    out: dict[tuple[int, str], str] = {}
    for r in rows:
        if r["entered_at"]:
            out[(int(r["job_id"]), str(r["new_status"]))] = r["entered_at"]
    return out


def _has_status_history(conn) -> bool:
    """Mirrors ``tracker.db._has_table(conn, 'status_history')`` without importing
    a private helper across the module boundary — same
    ``sqlite_master`` existence check ``entered_status_at`` itself gates on."""
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='status_history'"
    ).fetchone()
    return row is not None


@board_bp.get("/board")
def board():
    """The whole board in one call: every non-archived application bucketed into
    its funnel column, each card carrying its time-in-stage + valid forward moves.
    A row in an unknown/archived status is dropped from the board (group_by_status
    contract), never surfaced in a phantom column.

    Time-in-stage is resolved via ONE batched ``status_history`` query
    (:func:`_entered_status_at_batch`) rather than a per-card
    ``service.entered_status_at`` call, avoiding an N+1 connection+query pattern
    on boards with many cards."""
    rows = service.list_jobs()
    buckets = kanban_core.group_by_status(rows)
    all_ids = [row["id"] for status in kanban_core.COLUMNS for row in buckets[status]]
    entered_map = _entered_status_at_batch(all_ids)
    columns = []
    for status in kanban_core.COLUMNS:
        cards = []
        for row in buckets[status]:
            # Time in the CURRENT stage: the status_history entry timestamp when
            # the card entered `status` (None on a never-moved row -> the helper
            # falls back to the applied/added heuristic).
            entered_at = entered_map.get((row["id"], status))
            n = kanban_core.days_in_stage(row, entered_at=entered_at)
            card = app_row_list(row)
            card["days_in_stage"] = n
            card["days_label"] = kanban_core.days_label(n)
            card["forward_targets"] = kanban_core.forward_targets(status)
            cards.append(card)
        columns.append({
            "status": status,
            "label": db.STATUS_LABELS.get(status, status.title()),
            "cards": cards,
        })
    return jsonify({"ok": True, "columns": columns})
