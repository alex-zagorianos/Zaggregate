"""Top Picks route — the current AI recommendation shortlist over the inbox.

Read-only re-host of ``tracker.service.top_picks(limit)``: inbox rows in the
latest rec_batch, ordered by rank. ``limit`` semantics match the engine exactly:
default 10, ``0``/``all`` -> every ranked row (``top_picks(0)``).
"""
from __future__ import annotations

from flask import Blueprint, request, jsonify

from tracker import service
from ..serializers import inbox_row

toppicks_bp = Blueprint("webui_toppicks", __name__)


def _parse_limit(raw: str | None) -> int:
    """Parse the ``limit`` query param to the int ``top_picks`` expects. Default
    10; ``all`` (or ``0``/blank) -> 0 = every ranked row. A non-numeric junk value
    falls back to the default rather than erroring (inclusion-over-precision: never
    500 a read on a bad query string)."""
    if raw is None:
        return 10
    raw = raw.strip().lower()
    if raw in ("all", "0", ""):
        return 0
    try:
        n = int(raw)
    except ValueError:
        return 10
    return n if n > 0 else 0


@toppicks_bp.get("/toppicks")
def toppicks():
    limit = _parse_limit(request.args.get("limit"))
    rows = service.top_picks(limit)
    return jsonify({"ok": True, "rows": [inbox_row(r) for r in rows]})
