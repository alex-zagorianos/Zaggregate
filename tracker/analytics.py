"""Local job-search funnel analytics over the existing tracker tables.

Pure SQL aggregation — NO new tables, NO schema change. Reads applications +
status_history (see tracker/db.py) and reports the classic application funnel:
stage rollup, stage-to-stage conversion, response rate, and median time deltas
(applied -> phone_screen, applied -> rejected).

Every function takes a sqlite3.Connection so tests can pass a temp DB; the thin
``compute(db_path=None)`` opens the active project DB via tracker.db.get_conn.

Funnel order:  interested -> applied -> phone_screen -> interview -> offer -> accepted
Terminal (off-funnel): rejected, withdrawn, ghosted.

"Reached AT LEAST stage X" means the job's CURRENT status is stage-X-or-further
*or* its status_history shows it passed through X at some point — so a job that
is now `rejected` still counts toward every stage it demonstrably cleared first.

Defensive throughout: a missing status_history table, empty tables, NULL/blank
timestamps, and zero-denominator conversions all degrade to zeros / None medians
rather than raising. stdlib only.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from statistics import median
from typing import Optional

# Progress stages in order; index encodes "how far" a job has advanced.
# 'accepted' is the success terminal AFTER an offer, so it caps the funnel and
# offer->accepted becomes a reportable conversion (D1 P5).
FUNNEL = ["interested", "applied", "phone_screen", "interview", "offer", "accepted"]
TERMINAL = {"rejected", "withdrawn", "ghosted"}
_STAGE_INDEX = {s: i for i, s in enumerate(FUNNEL)}

# Response = an applied job that reached at least this stage.
_RESPONSE_STAGE = "phone_screen"


# ── helpers ───────────────────────────────────────────────────────────────────

def _has_table(conn: sqlite3.Connection, name: str) -> bool:
    try:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
        ).fetchone()
    except sqlite3.Error:
        return False
    return row is not None


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    try:
        return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
    except sqlite3.Error:
        return set()


def _parse_dt(value) -> Optional[datetime]:
    """Parse an ISO-8601 timestamp (status_history.changed_at, UTC) or a bare
    date (applications.date_added). Returns a tz-aware UTC datetime, or None on
    blank/garbage — never raises."""
    if not value:
        return None
    s = str(value).strip()
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s)
    except (ValueError, TypeError):
        # Bare date (YYYY-MM-DD) or unexpected format.
        for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S"):
            try:
                dt = datetime.strptime(s[: len(fmt) + 6], fmt)
                break
            except ValueError:
                continue
        else:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _rate(num: float, denom: float) -> float:
    """Safe ratio rounded to 4 dp; 0.0 when the denominator is zero."""
    if not denom:
        return 0.0
    return round(num / denom, 4)


def _load_applications(conn: sqlite3.Connection) -> list[dict]:
    """All tracked applications as dicts. Empty list if the table is absent."""
    if not _has_table(conn, "applications"):
        return []
    cols = _columns(conn, "applications")
    sel = [c for c in ("id", "status", "source", "date_added") if c in cols]
    if "id" not in sel:
        return []
    rows = conn.execute(f"SELECT {', '.join(sel)} FROM applications").fetchall()
    out = []
    for r in rows:
        d = {sel[i]: r[i] for i in range(len(sel))}
        out.append({
            "id": d.get("id"),
            "status": (d.get("status") or "").strip(),
            "source": (d.get("source") or "").strip(),
            "date_added": d.get("date_added"),
        })
    return out


def _load_history(conn: sqlite3.Connection) -> dict[int, list[dict]]:
    """status_history grouped by job_id, each list sorted by changed_at. Empty
    dict if the table is missing (older DBs / partial fixtures)."""
    if not _has_table(conn, "status_history"):
        return {}
    cols = _columns(conn, "status_history")
    if not {"job_id", "new_status", "changed_at"} <= cols:
        return {}
    rows = conn.execute(
        "SELECT job_id, new_status, changed_at FROM status_history"
    ).fetchall()
    hist: dict[int, list[dict]] = {}
    for job_id, new_status, changed_at in rows:
        hist.setdefault(job_id, []).append({
            "new_status": (new_status or "").strip(),
            "changed_at": changed_at,
            "_dt": _parse_dt(changed_at),
        })
    for lst in hist.values():
        lst.sort(key=lambda e: (e["_dt"] is None, e["_dt"] or datetime.min.replace(tzinfo=timezone.utc)))
    return hist


def _reached_stages(app: dict, events: list[dict]) -> set[str]:
    """Funnel stages a job has reached at least once: every stage <= its current
    funnel index, plus any stage that appears as a new_status in its history."""
    reached: set[str] = set()
    cur = app["status"]
    if cur in _STAGE_INDEX:
        idx = _STAGE_INDEX[cur]
        reached.update(FUNNEL[: idx + 1])
    for e in events:
        if e["new_status"] in _STAGE_INDEX:
            reached.add(e["new_status"])
    # Reaching any later stage implies passing through the earlier ones, even if
    # an intermediate transition was never logged (e.g. interested->interview).
    if reached:
        top = max(_STAGE_INDEX[s] for s in reached)
        reached.update(FUNNEL[: top + 1])
    return reached


def _first_time(events: list[dict], status: str) -> Optional[datetime]:
    """Earliest changed_at where new_status == status, or None."""
    times = [e["_dt"] for e in events if e["new_status"] == status and e["_dt"]]
    return min(times) if times else None


# ── public API ────────────────────────────────────────────────────────────────

def funnel(conn: sqlite3.Connection) -> dict:
    """Full funnel report over the tracker tables. See module docstring for the
    "reached at least" semantics. Never raises on empty/partial data."""
    apps = _load_applications(conn)
    hist = _load_history(conn)

    # Raw current-status counts (every status, including terminal ones).
    counts: dict[str, int] = {}
    for a in apps:
        st = a["status"] or "unknown"
        counts[st] = counts.get(st, 0) + 1

    # Per-stage "reached at least" rollup, in funnel order.
    reached_by_stage = {s: 0 for s in FUNNEL}
    response_to_days: list[float] = []
    rejection_days: list[float] = []
    for a in apps:
        events = hist.get(a["id"], [])
        for s in _reached_stages(a, events):
            reached_by_stage[s] += 1

        # applied -> first phone_screen (response latency).
        t_applied = _first_time(events, "applied")
        t_resp = _first_time(events, _RESPONSE_STAGE)
        if t_applied and t_resp and t_resp >= t_applied:
            response_to_days.append((t_resp - t_applied).total_seconds() / 86400.0)

        # applied -> first rejection (kill latency).
        t_reject = _first_time(events, "rejected")
        if t_applied and t_reject and t_reject >= t_applied:
            rejection_days.append((t_reject - t_applied).total_seconds() / 86400.0)

    stage_counts = [{"stage": s, "count": reached_by_stage[s]} for s in FUNNEL]

    conversions = []
    for i in range(len(FUNNEL) - 1):
        frm, to = FUNNEL[i], FUNNEL[i + 1]
        conversions.append({
            "from": frm,
            "to": to,
            "rate": _rate(reached_by_stage[to], reached_by_stage[frm]),
        })

    applied_n = reached_by_stage["applied"]
    response_rate = _rate(reached_by_stage[_RESPONSE_STAGE], applied_n)

    tracked_since = None
    added = [a["date_added"] for a in apps if a["date_added"]]
    if added:
        tracked_since = min(str(d) for d in added)

    return {
        "counts": counts,
        "stage_counts": stage_counts,
        "conversions": conversions,
        "response_rate": response_rate,
        "median_days_to_response": (
            round(median(response_to_days), 4) if response_to_days else None
        ),
        "median_days_to_rejection": (
            round(median(rejection_days), 4) if rejection_days else None
        ),
        "total_tracked": len(apps),
        "tracked_since": tracked_since,
    }


def by_source(conn: sqlite3.Connection) -> list[dict]:
    """Per applications.source breakdown: how many applied, how many advanced to
    interview-or-further, the source's interview_rate (interview+ / applied), and
    a low_n flag (<5 applied so the rate is noise). Sorted by applied desc then
    source name. Empty list on no data.

    The rate key is 'interview_rate' (D1 P5): it measures reaching INTERVIEW, a
    distinct metric from funnel()'s applied->phone_screen 'response_rate' — the
    two shared one name in the same dialog and were confusing."""
    apps = _load_applications(conn)
    if not apps:
        return []
    hist = _load_history(conn)

    agg: dict[str, dict] = {}
    for a in apps:
        src = a["source"] or "unknown"
        bucket = agg.setdefault(src, {"applied": 0, "interview_plus": 0})
        reached = _reached_stages(a, hist.get(a["id"], []))
        if "applied" in reached:
            bucket["applied"] += 1
        if "interview" in reached:
            bucket["interview_plus"] += 1

    out = []
    for src, b in agg.items():
        out.append({
            "source": src,
            "applied": b["applied"],
            "interview_plus": b["interview_plus"],
            "interview_rate": _rate(b["interview_plus"], b["applied"]),
            "low_n": b["applied"] < 5,
        })
    out.sort(key=lambda r: (-r["applied"], r["source"]))
    return out


def compute(db_path=None) -> dict:
    """Convenience wrapper for callers (GUI / CLI): open the active project DB
    (or `db_path` when given) via tracker.db and return both reports.

    Returns {"funnel": funnel(conn), "by_source": by_source(conn)}.
    """
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
        return {"funnel": funnel(conn), "by_source": by_source(conn)}
    finally:
        conn.close()
