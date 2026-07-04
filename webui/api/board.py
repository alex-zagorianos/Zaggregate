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
from ui import kanban_core
from ..serializers import app_row

board_bp = Blueprint("webui_board", __name__)


@board_bp.get("/board")
def board():
    """The whole board in one call: every non-archived application bucketed into
    its funnel column, each card carrying its time-in-stage + valid forward moves.
    A row in an unknown/archived status is dropped from the board (group_by_status
    contract), never surfaced in a phantom column."""
    rows = service.list_jobs()
    buckets = kanban_core.group_by_status(rows)
    columns = []
    for status in kanban_core.COLUMNS:
        cards = []
        for row in buckets[status]:
            # Time in the CURRENT stage: the status_history entry timestamp when
            # the card entered `status` (None on a never-moved row -> the helper
            # falls back to the applied/added heuristic).
            entered_at = service.entered_status_at(row["id"], status)
            n = kanban_core.days_in_stage(row, entered_at=entered_at)
            card = app_row(row)
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
