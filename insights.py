"""Job-search Insights: channel conversion + application cadence (B6 beta).

A thin, READ-ONLY reporting layer over the existing tracker tables (applications
+ status_history + interview_rounds — see tracker/db.py). It reuses
``tracker.analytics`` for the heavy funnel math (the reached-at-least-stage
rollup, per-source breakdown) and shapes it into the three views the Insights
tab renders, plus a cadence report analytics doesn't cover.

Nothing here writes; every function takes a ``sqlite3.Connection`` so tests can
pass a temp DB, and ``compute(db_path=None)`` opens the active project DB via
``tracker.db.get_conn`` (same convenience seam as ``analytics.compute``).

What the tracker actually stores (verified against tracker/db.py):
* ``applications.source`` EXISTS (``TEXT DEFAULT 'manual'``). ``inbox_track()``
  copies the inbox row's ``source`` onto the application, so tracked-from-inbox
  rows carry their true channel; a manual add is ``'manual'``. No fallback to
  the original inbox row is needed — the column is always populated. A blank/
  empty source (only possible on hand-crafted rows) is bucketed as ``'unknown'``
  honestly (mirrors ``analytics.by_source``).
* Interview reach = the funnel already counts a row that reached the
  ``interview`` stage (by current status OR a status_history transition); on top
  of that we count a row with ANY ``interview_rounds`` entry as having reached
  interview too, so a scheduled round advances the funnel even if the status lag.

Three views:
* ``funnel()``   — tracked -> applied -> interview -> offer/accepted counts + the
                   stage conversion rates, plus the ghosted count.
* ``by_source()``— per source: applied, interviews, interview_rate; ONLY sources
                   with >=1 applied (a source with nothing applied is noise).
* ``cadence()``  — applications/week from ``date_applied`` over the last N weeks,
                   the current week's count, the current streak of >=1-per-week
                   weeks, and the steady-cadence guidance band as constants.
"""
from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta, timezone

from tracker import analytics

# Steady-cadence guidance band (B6): the evidence-backed "consistency wins" range
# the tab surfaces. Constants, never a hardcoded per-source benchmark.
CADENCE_TARGET_MIN = 10
CADENCE_TARGET_MAX = 20

# Interview-ish statuses: a row currently at (or past) any of these has reached
# the interview stage even if the intermediate transition was never logged. This
# mirrors analytics.FUNNEL's ordering (phone_screen is a pre-interview response
# but NOT yet "interview"); the funnel rollup already handles status, so this set
# is only used to fold interview_rounds into the interview reach.
_INTERVIEW_STAGES = {"interview", "offer", "accepted"}


def _apps_with_interview_round(conn: sqlite3.Connection) -> set[int]:
    """app_ids that have at least one interview_rounds row. Empty set when the
    table is absent (older DBs / partial fixtures) — never raises."""
    if not analytics._has_table(conn, "interview_rounds"):
        return set()
    cols = analytics._columns(conn, "interview_rounds")
    if "app_id" not in cols:
        return set()
    rows = conn.execute(
        "SELECT DISTINCT app_id FROM interview_rounds WHERE app_id IS NOT NULL"
    ).fetchall()
    return {r[0] for r in rows}


def _reached_interview(app: dict, events: list[dict], round_ids: set[int]) -> bool:
    """True when a row demonstrably reached interview: it cleared the interview
    funnel stage (current status or a logged transition) OR it has a scheduled/
    completed interview round. Folding rounds in means a booked interview counts
    even if the status hasn't been moved yet."""
    if app["id"] in round_ids:
        return True
    reached = analytics._reached_stages(app, events)
    return "interview" in reached


def funnel(conn: sqlite3.Connection) -> dict:
    """Channel-agnostic funnel for the Insights top row.

    Counts (reached-at-least semantics, so a now-rejected row still counts toward
    every stage it cleared):
      * ``tracked``   — every tracked application.
      * ``applied``   — reached >= applied.
      * ``interview`` — reached the interview stage OR has any interview round.
      * ``offer``     — reached >= offer.
      * ``accepted``  — reached accepted (the success terminal).
      * ``ghosted``   — CURRENT status == 'ghosted' (a distinct terminal, not a
                        funnel stage; the employer went silent).

    Rates (each a safe 0..1 ratio, 0.0 on a zero denominator):
      * ``applied_rate``       applied / tracked
      * ``interview_rate``     interview / applied
      * ``offer_rate``         offer / interview
      * ``accepted_rate``      accepted / offer

    Read-only; never raises on empty/partial data (mirrors analytics.funnel)."""
    apps = analytics._load_applications(conn)
    hist = analytics._load_history(conn)
    round_ids = _apps_with_interview_round(conn)

    tracked = len(apps)
    applied = interview = offer = accepted = ghosted = 0
    for a in apps:
        events = hist.get(a["id"], [])
        reached = analytics._reached_stages(a, events)
        if a["status"] == "ghosted":
            ghosted += 1
        if "applied" in reached:
            applied += 1
        if _reached_interview(a, events, round_ids):
            interview += 1
        if "offer" in reached:
            offer += 1
        if "accepted" in reached:
            accepted += 1

    return {
        "tracked": tracked,
        "applied": applied,
        "interview": interview,
        "offer": offer,
        "accepted": accepted,
        "ghosted": ghosted,
        "applied_rate": analytics._rate(applied, tracked),
        "interview_rate": analytics._rate(interview, applied),
        "offer_rate": analytics._rate(offer, interview),
        "accepted_rate": analytics._rate(accepted, offer),
    }


def by_source(conn: sqlite3.Connection) -> list[dict]:
    """Per-source conversion for the "Where your interviews come from" table.

    One row per applications.source that has >=1 applied (a source with nothing
    applied is dropped — it can't have an interview_rate and only adds noise).
    Each row: ``source``, ``applied``, ``interviews`` (reached interview OR has a
    round), ``interview_rate`` (interviews / applied), and ``low_n`` (<5 applied,
    so the rate is statistically thin). Sorted by applied desc, then source name.

    A blank/empty source is bucketed as 'unknown' honestly. Read-only; [] on no
    data."""
    apps = analytics._load_applications(conn)
    if not apps:
        return []
    hist = analytics._load_history(conn)
    round_ids = _apps_with_interview_round(conn)

    agg: dict[str, dict] = {}
    for a in apps:
        src = a["source"] or "unknown"
        bucket = agg.setdefault(src, {"applied": 0, "interviews": 0})
        events = hist.get(a["id"], [])
        reached = analytics._reached_stages(a, events)
        if "applied" in reached:
            bucket["applied"] += 1
        if _reached_interview(a, events, round_ids):
            bucket["interviews"] += 1

    out = []
    for src, b in agg.items():
        if b["applied"] < 1:
            continue  # only sources with >=1 applied (contract)
        out.append({
            "source": src,
            "applied": b["applied"],
            "interviews": b["interviews"],
            "interview_rate": analytics._rate(b["interviews"], b["applied"]),
            "low_n": b["applied"] < 5,
        })
    out.sort(key=lambda r: (-r["applied"], r["source"]))
    return out


def _iso_week_start(d: date) -> date:
    """The Monday of d's ISO week (weeks are Monday-anchored for cadence)."""
    return d - timedelta(days=d.weekday())


def _parse_applied_date(value) -> date | None:
    """Parse an applications.date_applied ('YYYY-MM-DD', occasionally a full ISO
    timestamp) to a date, or None on blank/garbage. Reuses analytics._parse_dt so
    the two layers agree on timestamp handling."""
    dt = analytics._parse_dt(value)
    return dt.date() if dt is not None else None


def cadence(conn: sqlite3.Connection, weeks: int = 8, today: date | None = None) -> dict:
    """Weekly application cadence over the last ``weeks`` ISO weeks.

    Buckets applications by their ``date_applied`` into Monday-anchored weeks and
    reports, for the Insights cadence chart:
      * ``weeks`` — list oldest->newest of ``{week_start:'YYYY-MM-DD', count:int,
        current:bool}`` (exactly ``weeks`` entries, zero-filled).
      * ``current_week`` — applications submitted in the week containing today.
      * ``streak`` — how many consecutive weeks up to and including the current
        one had >=1 application (0 if the current week is empty).
      * ``per_week_avg`` — mean applications/week across the window (2 dp).
      * ``target_min`` / ``target_max`` — the 10..20 guidance band constants.

    Rows with no/blank ``date_applied`` (e.g. still 'interested', never applied)
    are ignored — cadence is about actually-submitted applications. Read-only;
    graceful on an empty table. ``today`` is injectable for deterministic tests."""
    if today is None:
        today = datetime.now(timezone.utc).date()
    weeks = max(1, int(weeks))

    current_start = _iso_week_start(today)
    # Oldest week start in the window: (weeks-1) weeks before the current one.
    window_starts = [current_start - timedelta(weeks=(weeks - 1 - i))
                     for i in range(weeks)]
    window_set = set(window_starts)
    counts = {ws: 0 for ws in window_starts}

    applied_dates: list[date] = []
    if analytics._has_table(conn, "applications"):
        cols = analytics._columns(conn, "applications")
        if "date_applied" in cols:
            for (val,) in conn.execute(
                "SELECT date_applied FROM applications "
                "WHERE date_applied IS NOT NULL AND date_applied != ''"
            ).fetchall():
                d = _parse_applied_date(val)
                if d is not None:
                    applied_dates.append(d)

    for d in applied_dates:
        ws = _iso_week_start(d)
        if ws in window_set:
            counts[ws] += 1

    week_rows = [{
        "week_start": ws.isoformat(),
        "count": counts[ws],
        "current": ws == current_start,
    } for ws in window_starts]

    current_week = counts[current_start]

    # Streak = consecutive weeks with >=1 application counting back from the
    # current week (inclusive). Stops at the first empty week or the window edge.
    streak = 0
    for ws in reversed(window_starts):
        if counts[ws] >= 1:
            streak += 1
        else:
            break

    total = sum(counts.values())
    per_week_avg = round(total / weeks, 2) if weeks else 0.0

    return {
        "weeks": week_rows,
        "current_week": current_week,
        "streak": streak,
        "per_week_avg": per_week_avg,
        "target_min": CADENCE_TARGET_MIN,
        "target_max": CADENCE_TARGET_MAX,
    }


def compute(db_path=None, weeks: int = 8) -> dict:
    """Open the active project DB (or ``db_path``) and return all three Insights
    views in one call: ``{"funnel":..., "by_source":..., "cadence":...}``. The
    web route (webui/api/insights.py) and any CLI caller use this so the DB seam
    lives in one place (mirrors analytics.compute)."""
    from tracker import db as _db

    if db_path is not None:
        prev = _db.DB_PATH
        _db.DB_PATH = str(db_path)
        try:
            conn = _db.get_conn()
        finally:
            _db.DB_PATH = prev
    else:
        conn = _db.get_conn()
    try:
        return {
            "funnel": funnel(conn),
            "by_source": by_source(conn),
            "cadence": cadence(conn, weeks=weeks),
        }
    finally:
        conn.close()
