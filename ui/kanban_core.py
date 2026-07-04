"""Tk-free core of the Kanban board — the pure funnel helpers the web API and
the Tk board BOTH need, extracted so the browser layer can reuse the exact
column order and move/day math without importing tkinter (importing tkinter
server-side is pointless and can fail on a headless box).

``ui/kanban.py`` re-exports every public name from this module and adds only the
Tk ``KanbanTab`` widget on top, so existing callers/tests that reach
``kanban.COLUMNS`` / ``kanban.forward_targets`` / ``kanban.days_in_stage`` /
``kanban.days_label`` / ``kanban.group_by_status`` keep working byte-for-byte
(the S36 ``source_keys_core`` precedent).

Design constraints (repo rules): no display dependency, pure/deterministic
(``today`` and ``entered_at`` are injectable for tests), inclusion-over-precision
(a row in an unknown status is dropped from the board, never crashes the render).
"""
from __future__ import annotations

# Column order. The eight named funnel stages (SB-5), plus 'withdrawn' so no
# tracked application is ever invisible on the board (it's a real status a row
# can hold). Kept as a module constant so the headless tests assert the layout
# without a display, and the web /api/board serializes columns in this order.
COLUMNS = ["interested", "applied", "phone_screen", "interview", "offer",
           "accepted", "rejected", "withdrawn", "ghosted"]

# Terminal / outcome stages: a card here is done moving forward, so the board
# offers no "advance" affordance (never a downgrade). Editing still lets a user
# correct a status via the dialog if they truly need to.
_TERMINAL = frozenset({"accepted", "rejected", "withdrawn", "ghosted"})

# The forward moves the board offers from each stage. Progression stages advance
# to the next funnel step AND to any outcome; the model in tracker.db permits any
# status set, but we only surface non-downgrading choices so the board can't be
# used to walk an application backwards by accident.
_OUTCOMES = ["offer", "accepted", "rejected", "withdrawn", "ghosted"]


def forward_targets(status: str) -> list[str]:
    """The statuses the board lets a card in ``status`` move to — forward funnel
    step(s) plus outcomes, de-duplicated, never the card's own status, and never a
    downgrade. Terminal stages return [] (no advance offered). Pure/testable."""
    if status in _TERMINAL:
        return []
    order = ["interested", "applied", "phone_screen", "interview", "offer",
             "accepted"]
    out: list[str] = []
    if status in order:
        idx = order.index(status)
        # the immediate next funnel step (if any)
        if idx + 1 < len(order):
            out.append(order[idx + 1])
    # plus every outcome that isn't the current status and isn't already queued
    for s in _OUTCOMES:
        if s != status and s not in out:
            out.append(s)
    return out


def days_in_stage(row: dict, today=None, entered_at: str | None = None) -> int | None:
    """Whole days the application has sat in its CURRENT status. Returns None when
    no usable date is present. ``today`` is injectable for deterministic tests.

    Precedence for the reference date:
      1. ``entered_at`` — the status_history timestamp of when the card actually
         entered its current status (passed in by the widget via
         tracker.service.entered_status_at). This is the true "days here" clock:
         a card that applied 30 days ago but moved to 'interview' yesterday reads
         "1 day here", not "30".
      2. Fallback (no transition history — e.g. a row created directly at its
         status): the later-of-applied/added heuristic. date_applied is the
         meaningful clock once applied; before that, date_added.
    """
    from datetime import date
    if today is None:
        today = date.today()
    elif isinstance(today, str):
        try:
            today = date.fromisoformat(today[:10])
        except ValueError:
            return None
    ref = (entered_at or "").strip()
    if not ref:
        # No entered-this-status timestamp: fall back to the row's own dates.
        status = (row.get("status") or "")
        if status not in ("interested",):
            ref = (row.get("date_applied") or "").strip()
        if not ref:
            ref = (row.get("date_added") or "").strip()
    if not ref:
        return None
    try:
        ref_date = date.fromisoformat(ref[:10])
    except ValueError:
        return None
    delta = (today - ref_date).days
    return delta if delta >= 0 else 0


def days_label(n: int | None) -> str:
    """A compact 'Nd here' badge for a day count (or '' when unknown)."""
    if n is None:
        return ""
    if n == 0:
        return "today"
    if n == 1:
        return "1 day"
    return f"{n} days"


def group_by_status(rows: list[dict]) -> dict[str, list[dict]]:
    """Bucket application rows into ``{status: [rows...]}`` for every COLUMN.
    A row whose status isn't a known column is dropped from the board (it would be
    an archived/unknown state); every known column key is always present (possibly
    empty). Newest-first within a column (rows arrive date_added DESC from db)."""
    buckets: dict[str, list[dict]] = {c: [] for c in COLUMNS}
    for r in rows:
        s = r.get("status")
        if s in buckets:
            buckets[s].append(r)
    return buckets
