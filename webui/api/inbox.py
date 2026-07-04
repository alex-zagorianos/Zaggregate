"""Inbox triage routes (Phase 1: track + dismiss).

Two mutating actions that move a row OUT of the inbox, mirroring the tk Inbox/
Top-Picks triage keys:

* ``POST /api/inbox/<id>/track``   -> promote to a tracked application (interested)
* ``POST /api/inbox/<id>/dismiss`` -> hide from all future searches/daily runs

Both re-host the engine seam ``tracker.service`` verbatim (no hand-rolled SQL),
are origin-gated (they mutate the DB), and return a clean 404 for an unknown id.
``track_job`` already reports a missing row as ``None``; ``dismiss_job`` is silent
on a missing row, so we existence-check via ``service.inbox_exists`` first so a
bad id is a 404 rather than a silent 200.

Phase 3 grows this module with the full Inbox list/filters/fit/export/import/undo
surface; this file stays the home for those.
"""
from __future__ import annotations

from flask import Blueprint, jsonify

from tracker import service
from ..security import require_local_origin

inbox_bp = Blueprint("webui_inbox", __name__)


@inbox_bp.post("/inbox/<int:inbox_id>/track")
@require_local_origin
def track(inbox_id: int):
    """Promote an inbox row to a tracked application. 404 if the row is gone."""
    app_id = service.track_job(inbox_id)
    if app_id is None:
        return jsonify({"ok": False, "error": "unknown inbox row"}), 404
    return jsonify({"ok": True, "app_id": app_id})


@inbox_bp.post("/inbox/<int:inbox_id>/dismiss")
@require_local_origin
def dismiss(inbox_id: int):
    """Dismiss an inbox row (hidden from future runs). 404 if the row is gone."""
    if not service.inbox_exists(inbox_id):
        return jsonify({"ok": False, "error": "unknown inbox row"}), 404
    service.dismiss_job(inbox_id)
    return jsonify({"ok": True})
