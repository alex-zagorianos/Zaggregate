"""Tk-free port of ``ui.tab_inbox.InboxTab._filtered`` — the Inbox view filters.

These are the *same* view-filter semantics the tk InboxTab applies client-side
over its cached ``inbox_all()`` snapshot, lifted out of the Tk widget so the web
API can apply them server-side with byte-for-byte identical inclusion logic. The
tk module keeps its own copy (this is a parallel extraction, NOT a re-export of a
Tk method — the original ``_filtered`` reads ``tk.StringVar``/``BooleanVar``
palette state and can't be called without a Tk root); the two are kept in lockstep
by the parity tests in ``tests/webui/test_inbox_filters.py``.

**Inclusion over precision (repo CLAUDE.md):** every function here is a VIEW
filter — it decides what the caller *sees*, never what exists. Nothing is deleted;
dismiss/track/view-mode are the only drop mechanisms. When a filter param is
absent/blank it is a no-op (the row is kept). Ambiguity keeps the row.

Filter parity map (tk ``_filtered`` -> this module), all applied as AND:

* ``min_score``      -> ``row["score"] >= min_score``           (tk: int(minscore))
* ``sources`` (csv)  -> ``row["source"] in sources``            (tk: single combobox == source; the web widens to a set)
* ``size`` (letter)  -> ``_size_letter(board_count) == size``   (tk: size combobox)
* ``unscored_only``  -> ``row["fit"] < 0``                      (tk: "Unscored only")
* ``new_only``       -> row is in the latest new_batch          (tk: "New only")
* ``hide_stale``     -> ``ghost_score(row)["level"] != "stale"`` (tk: "Hide stale")
* ``pay_floor``      -> disclosed comp top >= floor             (tk: "Meets pay floor"; undisclosed HIDDEN)
* ``location_mode``  -> ``location_visible(...)`` unless "All locations" / no home
* ``q``              -> substring in title OR company           (tk: "Find")

The one deliberate semantic WIDENING vs tk: ``sources`` is a set (csv) so the web
UI can multi-select, where the tk combobox picks exactly one. A single-element set
reproduces the tk single-select exactly; the empty/omitted set is the tk "All".
Everything else is a faithful port, including the pay-floor rule that HIDES rows
with no disclosed pay (the one place the Inbox intentionally hides on an explicit
opt-in filter — mirrors tk exactly, and it is opt-in + reversible, so it does not
violate inclusion-over-precision).
"""
from __future__ import annotations

import json
from typing import Iterable, Optional

from geo.filter import location_visible
from match import comp as _compmod
from match import ghost as _ghostmod

# ── freshness helpers ─────────────────────────────────────────────────────────
# Tk-free copies of ui.tab_inbox's module-level ``_row_new_batch`` /
# ``_latest_new_batch`` / ``_is_new_row``. They are duplicated here (not imported
# from ui.tab_inbox) BECAUSE importing that module pulls in tkinter, and the webui
# package must stay GUI-free (tests/webui/test_import_isolation.py enforces this in
# a fresh interpreter). The logic is pure (parse the extras JSON blob, compare the
# ``new_batch`` stamp) and byte-identical to the tk versions — the parity test in
# tests/webui/test_inbox_filters.py asserts these agree with ui.tab_inbox's copies
# so the two implementations can never drift.


def _row_new_batch(row) -> str:
    """The freshness batch stamped on an inbox row's extras ('' if none)."""
    raw = row.get("extras")
    if not raw:
        return ""
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return ""
    return data.get("new_batch", "") if isinstance(data, dict) else ""


def _latest_new_batch(rows) -> "str | None":
    """Most recent freshness batch across rows (None if none stamped)."""
    batches = [b for b in (_row_new_batch(r) for r in rows) if b]
    return max(batches) if batches else None


def _is_new_row(row, latest) -> bool:
    return bool(latest) and _row_new_batch(row) == latest


def size_letter(board_count) -> str:
    """Company-size letter (S/M/L/XL/?) from a careers-board posting count —
    the Tk-free twin of ``InboxTab._size_letter``. ``None``/absent -> '?'."""
    bc = board_count if board_count is not None else -1
    try:
        bc = int(bc)
    except (TypeError, ValueError):
        return "?"
    if bc < 0:
        return "?"
    if bc <= 30:
        return "S"
    if bc <= 100:
        return "M"
    if bc <= 250:
        return "L"
    return "XL"


def comp_for(row: dict) -> dict:
    """Normalized disclosed-pay dict for a row (``match.comp.normalize_comp``).
    Cached on ``row['_comp']`` exactly like tk's ``refresh()`` does, so repeated
    filter passes over the same snapshot are cheap."""
    c = row.get("_comp")
    if c is None:
        c = _compmod.normalize_comp(row)
        row["_comp"] = c
    return c


def _meets_pay_floor(row: dict, floor: int) -> bool:
    """tk parity: a row meets the floor only when its comp is DISCLOSED and the
    top of its range (max, else min) is >= floor. Undisclosed pay is hidden by
    this opt-in filter (mirrors ``InboxTab._filtered``'s ``_meets``)."""
    c = comp_for(row)
    if not c or not c.get("disclosed"):
        return False
    top = c["max"] if c.get("max") is not None else c.get("min")
    return top is not None and top >= floor


def filter_rows(
    rows: list[dict],
    *,
    min_score: Optional[int] = None,
    sources: Optional[Iterable[str]] = None,
    size: Optional[str] = None,
    unscored_only: bool = False,
    new_only: bool = False,
    hide_stale: bool = False,
    pay_floor: Optional[int] = None,
    location_mode: Optional[str] = None,
    home_area: str = "",
    has_home: bool = True,
    remote_ok: bool = True,
    q: Optional[str] = None,
    all_rows: Optional[list[dict]] = None,
) -> list[dict]:
    """Apply the Inbox view filters to ``rows`` and return the surviving subset,
    preserving input order. A faithful port of ``InboxTab._filtered``.

    ``all_rows`` is the UNFILTERED snapshot used to resolve the "latest new batch"
    for ``new_only`` (tk computes it over ``self._all``, not the filtered view, so
    narrowing another filter can't change which batch counts as "new"). Defaults
    to ``rows`` when not supplied.

    Every param defaults to a no-op: omit it and no rows are dropped for it.

    Sample-inbox bypass (tk parity, ``InboxTab._filtered`` L661-669): when the WHOLE
    row set is the bundled demo sample, return it completely unfiltered. Its varied
    locations/scores ARE the demo (they teach the location-clean, Score-vs-Fit split),
    so a first-run user's default filter-bar state (a leftover Local-only mode or a
    nonzero min_score from a previous project) must never whittle it down before they
    have run a real search. Gate on the rows ACTUALLY being demo rows (``is_demo``),
    not a flag, so a caller that mixes in real rows is never left unfiltered.
    """
    if rows and all(r.get("is_demo") for r in rows):
        return list(rows)

    out = rows
    snapshot = all_rows if all_rows is not None else rows

    if min_score is not None:
        out = [r for r in out if (r.get("score", -1) or -1) >= min_score]

    src_set = {s for s in (sources or []) if s}
    if src_set:
        out = [r for r in out if r.get("source") in src_set]

    if size and size != "All":
        out = [r for r in out if size_letter(r.get("board_count", -1)) == size]

    if unscored_only:
        out = [r for r in out if (r.get("fit", -1) or -1) < 0]

    if new_only:
        latest = _latest_new_batch(snapshot)
        out = [r for r in out if _is_new_row(r, latest)]

    if hide_stale:
        out = [r for r in out
               if _ghostmod.ghost_score(r).get("level") != "stale"]

    if pay_floor:
        out = [r for r in out if _meets_pay_floor(r, pay_floor)]

    # Location: a local-focus mode only applies when there IS a home metro to key
    # on (tk: ``getattr(self, "_has_home", True)``); otherwise behave as "All
    # locations" so we never silently empty the view against a blank home string.
    if location_mode and location_mode != "All locations" and has_home:
        out = [r for r in out
               if location_visible(r.get("location") or "", r.get("title") or "",
                                   home_area, location_mode, remote_ok=remote_ok)]

    if q:
        needle = q.strip().lower()
        if needle:
            out = [r for r in out
                   if needle in (r.get("title") or "").lower()
                   or needle in (r.get("company") or "").lower()]

    return out
