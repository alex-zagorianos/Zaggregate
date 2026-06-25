import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import workspace
from models import normalize_url  # single source of truth for URL canonicalization

# None = resolve the active project's DB at call-time (root tracker.db until a
# project workspace exists). Tests set this to a temp path to override.
DB_PATH = None

# Bump whenever the schema (tables/columns/indexes below) changes. init_db()
# stores this in PRAGMA user_version after a successful setup; if the db already
# matches, init_db skips the whole probe + ALTER scan (cheap, concurrency-safe).
SCHEMA_VERSION = 3


def current_db_path() -> Path:
    return Path(DB_PATH) if DB_PATH is not None else workspace.db_path()

STATUSES = ["interested", "applied", "phone_screen", "interview", "offer", "rejected", "withdrawn"]
STATUS_LABELS = {
    "interested":  "Interested",
    "applied":     "Applied",
    "phone_screen":"Phone Screen",
    "interview":   "Interview",
    "offer":       "Offer",
    "rejected":    "Rejected",
    "withdrawn":   "Withdrawn",
}

# Columns added after the original schema shipped. init_db() ALTERs any that are
# missing, so an existing tracker.db upgrades in place without data loss.
_EXTRA_COLUMNS = {
    "follow_up_date": "TEXT DEFAULT ''",   # next-action / reminder date
    "deadline":       "TEXT DEFAULT ''",   # application deadline
    "contact":        "TEXT DEFAULT ''",   # recruiter / hiring contact
    "description":    "TEXT DEFAULT ''",   # saved JD snapshot (postings vanish)
    "resume_path":    "TEXT DEFAULT ''",   # generated resume tied to this app
    "cover_path":     "TEXT DEFAULT ''",   # generated cover letter tied to this app
    "score":          "INTEGER DEFAULT -1",  # local match score (match/scorer)
    "fit_score":      "INTEGER DEFAULT -1",  # Claude fit score (claude_bridge)
    "fit_rationale":  "TEXT DEFAULT ''",     # Claude's 2-line why / red flags
    "archived":       "INTEGER DEFAULT 0",   # soft-delete: hidden from normal views
}

_EDITABLE = {
    "status", "notes", "date_applied", "title", "company", "location", "url",
    "salary_text", "follow_up_date", "deadline", "contact", "description", "resume_path",
    "cover_path", "score", "fit_score", "fit_rationale",
}


def get_conn():
    # The headless daily_run and the GUI write the same project DB. WAL lets
    # reads proceed during a write, and busy_timeout waits out brief lock
    # contention instead of raising 'database is locked'.
    conn = sqlite3.connect(str(current_db_path()), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _existing_columns(conn) -> set[str]:
    return {r["name"] for r in conn.execute("PRAGMA table_info(applications)")}


def init_db() -> bool:
    """Create/upgrade the schema. Gated on PRAGMA user_version: if the db is
    already at SCHEMA_VERSION, skip the probe + ALTER scan entirely. Returns
    True when migration work ran, False when the fast path was taken."""
    with get_conn() as conn:
        if conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION:
            return False  # already current — no probe, no ALTER scan
        old_version = conn.execute("PRAGMA user_version").fetchone()[0]
        if old_version and old_version < SCHEMA_VERSION:
            import shutil
            src = current_db_path()
            try:
                shutil.copy2(str(src), str(src) + f".bak-v{old_version}")
            except OSError:
                pass  # backup is best-effort; never block the migration
        conn.execute("""
            CREATE TABLE IF NOT EXISTS applications (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                title        TEXT NOT NULL,
                company      TEXT NOT NULL,
                location     TEXT    DEFAULT '',
                url          TEXT    DEFAULT '',
                salary_text  TEXT    DEFAULT '',
                source       TEXT    DEFAULT 'manual',
                status       TEXT    DEFAULT 'interested',
                date_added   TEXT    NOT NULL,
                date_applied TEXT    DEFAULT '',
                notes        TEXT    DEFAULT ''
            )
        """)
        existing = _existing_columns(conn)
        for col, decl in _EXTRA_COLUMNS.items():
            if col not in existing:
                conn.execute(f"ALTER TABLE applications ADD COLUMN {col} {decl}")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_status ON applications(status)")
        # Jobs the user explicitly dismissed — filtered out of future searches.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS dismissed (
                url        TEXT PRIMARY KEY,
                dismissed_at TEXT NOT NULL
            )
        """)
        # Inbox: scored results from the daily headless run, awaiting triage.
        # norm_url is the dedup key, so re-runs can't double-insert a posting.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS inbox (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                norm_url    TEXT UNIQUE NOT NULL,
                title       TEXT NOT NULL,
                company     TEXT NOT NULL,
                location    TEXT DEFAULT '',
                url         TEXT DEFAULT '',
                salary_text TEXT DEFAULT '',
                description TEXT DEFAULT '',
                source      TEXT DEFAULT '',
                score       INTEGER DEFAULT -1,
                score_notes TEXT DEFAULT '',
                fit         INTEGER DEFAULT -1,
                fit_why     TEXT DEFAULT '',
                created     TEXT DEFAULT '',
                date_added  TEXT NOT NULL
            )
        """)
        # Inbox columns added after the original schema shipped (same in-place
        # upgrade pattern as _EXTRA_COLUMNS above, but for the inbox table).
        inbox_existing = {r["name"] for r in conn.execute("PRAGMA table_info(inbox)")}
        for col, decl in {"board_count": "INTEGER DEFAULT -1"}.items():
            if col not in inbox_existing:
                conn.execute(f"ALTER TABLE inbox ADD COLUMN {col} {decl}")
        # Round-robin window orders by company; without this index every render
        # does a full partition sort over the whole inbox.
        conn.execute("CREATE INDEX IF NOT EXISTS idx_inbox_company ON inbox(company)")
        # Health beacon: one row per daily_run so the GUI can show a last-run
        # OK/FAILED badge and the run can be diagnosed after the fact.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS runs (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                project       TEXT DEFAULT '',
                started_at    TEXT NOT NULL,
                finished_at   TEXT DEFAULT '',
                status        TEXT DEFAULT 'running',
                source_counts TEXT DEFAULT '',
                error         TEXT DEFAULT ''
            )
        """)
        # Status transition log for funnel analytics (response rate,
        # time-to-response). One row per real status change. (delegate T4)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS status_history (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id      INTEGER NOT NULL,
                old_status  TEXT,
                new_status  TEXT NOT NULL,
                changed_at  TEXT NOT NULL
            )
        """)
        # v3 (WS-3): round-trip extras blob + score-change audit/undo log.
        inbox_existing_v3 = {r["name"] for r in conn.execute("PRAGMA table_info(inbox)")}
        if "extras" not in inbox_existing_v3:
            conn.execute("ALTER TABLE inbox ADD COLUMN extras TEXT DEFAULT ''")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS score_history (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                inbox_id  INTEGER NOT NULL,
                job_key   TEXT DEFAULT '',
                old_fit   INTEGER,
                new_fit   INTEGER,
                old_score INTEGER,
                source    TEXT DEFAULT '',
                ts        TEXT NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_score_history_inbox "
                     "ON score_history(inbox_id)")
        conn.execute("PRAGMA user_version = %d" % SCHEMA_VERSION)
        conn.commit()
        return True


def add_job(title, company, location="", url="", salary_text="",
            source="manual", status="interested", date_added="",
            date_applied="", notes="", **extra):
    from datetime import date
    if not date_added:
        date_added = date.today().isoformat()
    cols = ["title", "company", "location", "url", "salary_text", "source",
            "status", "date_added", "date_applied", "notes"]
    vals = [title, company, location, url, salary_text, source,
            status, date_added, date_applied, notes]
    for k, v in extra.items():
        if k in _EXTRA_COLUMNS:
            cols.append(k)
            vals.append(v)
    placeholders = ",".join("?" for _ in cols)
    with get_conn() as conn:
        cur = conn.execute(
            f"INSERT INTO applications ({','.join(cols)}) VALUES ({placeholders})",
            vals,
        )
        conn.commit()
        return cur.lastrowid


def get_all(status_filter=None):
    """Active (non-archived) applications, newest first. status_filter="archived"
    returns only archived rows; any other status filters within non-archived."""
    with get_conn() as conn:
        if status_filter == "archived":
            rows = conn.execute(
                "SELECT * FROM applications WHERE archived=1 ORDER BY date_added DESC"
            ).fetchall()
        elif status_filter and status_filter != "all":
            rows = conn.execute(
                "SELECT * FROM applications WHERE status=? AND archived=0 "
                "ORDER BY date_added DESC",
                (status_filter,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM applications WHERE archived=0 ORDER BY date_added DESC"
            ).fetchall()
    return [dict(r) for r in rows]


def count_followups_due(today=None):
    """Number of active (non-archived) applications whose follow_up_date has
    arrived — for the Tracker header nudge. A targeted COUNT so the GUI no longer
    pulls the whole table into Python just to tally this (GUI-10)."""
    from datetime import date
    if today is None:
        today = date.today().isoformat()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM applications "
            "WHERE archived=0 AND follow_up_date IS NOT NULL AND follow_up_date != '' "
            "AND follow_up_date <= ? "
            "AND status IN ('applied', 'phone_screen', 'interview')",
            (today,),
        ).fetchone()
    return int(row[0])


def followups_due(within_days=0, today=None, include_deadlines=True):
    """Active applications needing attention soon, for the 'Due' view. Returns the
    actual rows (count_followups_due only tallies): every non-archived application
    whose follow_up_date is due (status applied/phone_screen/interview) and, when
    include_deadlines, whose application deadline is approaching for a not-yet-applied
    role (status interested/applied). `within_days` widens the window (0 = due today
    or overdue). Each row gains 'due_kind' ('follow-up'|'deadline') and 'due_date';
    sorted soonest-first. Snooze = update_job(id, follow_up_date=<later>)."""
    from datetime import date, timedelta
    if today is None:
        today = date.today()
    elif isinstance(today, str):
        today = date.fromisoformat(today)
    horizon = (today + timedelta(days=within_days)).isoformat()
    out, seen = [], set()
    with get_conn() as conn:
        for r in conn.execute(
            "SELECT * FROM applications WHERE archived=0 "
            "AND follow_up_date IS NOT NULL AND follow_up_date != '' "
            "AND follow_up_date <= ? "
            "AND status IN ('applied','phone_screen','interview') "
            "ORDER BY follow_up_date",
            (horizon,),
        ).fetchall():
            d = dict(r)
            d["due_kind"], d["due_date"] = "follow-up", r["follow_up_date"]
            out.append(d)
            seen.add(r["id"])
        if include_deadlines:
            for r in conn.execute(
                "SELECT * FROM applications WHERE archived=0 "
                "AND deadline IS NOT NULL AND deadline != '' "
                "AND deadline <= ? "
                "AND status IN ('interested','applied') "
                "ORDER BY deadline",
                (horizon,),
            ).fetchall():
                if r["id"] in seen:
                    continue
                d = dict(r)
                d["due_kind"], d["due_date"] = "deadline", r["deadline"]
                out.append(d)
    out.sort(key=lambda d: (d["due_date"], d["due_kind"]))
    return out


def get_counts():
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT status, COUNT(*) as n FROM applications "
            "WHERE archived=0 GROUP BY status"
        ).fetchall()
        archived = conn.execute(
            "SELECT COUNT(*) FROM applications WHERE archived=1"
        ).fetchone()[0]
    counts = {s: 0 for s in STATUSES}
    total = 0
    for r in rows:
        counts[r["status"]] = r["n"]
        total += r["n"]
    counts["all"] = total
    counts["archived"] = archived
    return counts


def update_job(job_id, **fields):
    from datetime import datetime, timezone
    updates = {k: v for k, v in fields.items() if k in _EDITABLE}
    if not updates:
        return
    set_clause = ", ".join(f"{k}=?" for k in updates)
    with get_conn() as conn:
        # Record a status transition (old->new) before applying it, so the
        # status_history funnel reflects every real change. (delegate T4)
        if "status" in updates:
            row = conn.execute(
                "SELECT status FROM applications WHERE id=?", (job_id,)
            ).fetchone()
            if row and row["status"] != updates["status"]:
                conn.execute(
                    "INSERT INTO status_history "
                    "(job_id, old_status, new_status, changed_at) VALUES (?,?,?,?)",
                    (job_id, row["status"], updates["status"],
                     datetime.now(timezone.utc).isoformat()),
                )
        conn.execute(
            f"UPDATE applications SET {set_clause} WHERE id=?",
            (*updates.values(), job_id),
        )
        conn.commit()


def archive_job(job_id):
    """Soft-delete: hide from normal tracker views/counts but keep the row (and
    its URL in the dedup set, so it won't resurface in searches)."""
    with get_conn() as conn:
        conn.execute("UPDATE applications SET archived=1 WHERE id=?", (job_id,))
        conn.commit()


def unarchive_job(job_id):
    with get_conn() as conn:
        conn.execute("UPDATE applications SET archived=0 WHERE id=?", (job_id,))
        conn.commit()


def delete_job(job_id):
    """Permanent delete — reachable only from the archive view in the GUI."""
    with get_conn() as conn:
        conn.execute("DELETE FROM applications WHERE id=?", (job_id,))
        conn.commit()


def get_job(job_id):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM applications WHERE id=?", (job_id,)
        ).fetchone()
    return dict(row) if row else None


# ── Cross-run dedup ───────────────────────────────────────────────────────────

# normalize_url is imported from models (single source of truth) so the inbox
# dedup key always matches the search-side identity key. This was a parity copy;
# deduped 2026-06-24 after verifying byte-identical output for all inputs.


def tracked_urls() -> set[str]:
    with get_conn() as conn:
        rows = conn.execute("SELECT url FROM applications WHERE url != ''").fetchall()
    return {normalize_url(r["url"]) for r in rows}


def dismiss_url(url: str):
    from datetime import datetime, timezone
    if not url:
        return
    with get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO dismissed (url, dismissed_at) VALUES (?,?)",
            (normalize_url(url), datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()


def dismissed_urls() -> set[str]:
    with get_conn() as conn:
        rows = conn.execute("SELECT url FROM dismissed").fetchall()
    return {r["url"] for r in rows}


def seen_urls() -> set[str]:
    """All normalized URLs to hide from new searches: tracked + dismissed."""
    return tracked_urls() | dismissed_urls()


# ── Inbox (daily-run results awaiting triage) ─────────────────────────────────

def inbox_add_many(jobs, per_company_cap: int = 0, new_batch: str = "") -> int:
    """Insert JobResults into the inbox; silently skips postings already in the
    inbox, tracker, or dismissed list. Returns how many were actually added.

    per_company_cap > 0 enforces the cap against the PERSISTED inbox: a company
    already at N rows can only take (cap - N) more, so a board can't accrue
    cap rows per run and pile up over many runs. jobs is assumed best-first so
    the surviving rows are each company's top matches. 0 disables the cap.

    new_batch (set by daily_run): when truthy, a freshly-inserted job carrying
    is_new=True gets its extras stamped with {"new_batch": new_batch}, so the
    GUI "New only" filter can surface jobs new since the last run. Schema-free
    (rides the existing extras JSON, like Top Picks' rank)."""
    from datetime import date
    import json
    seen = seen_urls()
    today = date.today().isoformat()
    # Start the running tally from what's already persisted so the cap spans runs.
    per_company = inbox_company_counts() if per_company_cap > 0 else {}
    added = 0
    with get_conn() as conn:
        for j in jobs:
            norm = normalize_url(j.url)
            if not norm or norm in seen:
                continue
            if per_company_cap > 0:
                key = (j.company or "").lower().strip()
                if per_company.get(key, 0) >= per_company_cap:
                    continue
            cur = conn.execute(
                """INSERT OR IGNORE INTO inbox
                   (norm_url, title, company, location, url, salary_text,
                    description, source, score, score_notes, created, date_added,
                    board_count)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (norm, j.title, j.company, j.location, j.url,
                 j.salary_display(), (j.description or "")[:5000],
                 j.source_api, j.score, j.score_notes, j.created, today,
                 getattr(j, "board_count", -1)),
            )
            if cur.rowcount:
                if new_batch and getattr(j, "is_new", False):
                    conn.execute("UPDATE inbox SET extras=? WHERE id=?",
                                 (json.dumps({"new_batch": new_batch}), cur.lastrowid))
                if per_company_cap > 0:
                    per_company[key] = per_company.get(key, 0) + 1
            added += cur.rowcount
        conn.commit()
    return added


def inbox_all(order: str = "roundrobin") -> list[dict]:
    """Inbox rows for triage.

    order="roundrobin" (default): best job from each company first, then each
    company's 2nd-best, etc. — one mega-board can't wallpaper the top of the
    list. order="score": raw fit-else-score ranking.
    """
    rank = "CASE WHEN fit >= 0 THEN fit ELSE score END"
    # date_added is date-only, so within a single run it's a no-op tiebreaker and
    # intra-run order is undefined. Prefer the posting's full timestamp (created)
    # and only fall back to date_added when created is blank.
    recency = "COALESCE(NULLIF(created,''), date_added) DESC"
    if order == "roundrobin":
        sql = (
            f"SELECT *, ROW_NUMBER() OVER "
            f"(PARTITION BY company ORDER BY {rank} DESC, {recency}) AS rk "
            f"FROM inbox ORDER BY rk, {rank} DESC, {recency}"
        )
    else:
        sql = f"SELECT * FROM inbox ORDER BY {rank} DESC, {recency}"
    with get_conn() as conn:
        rows = conn.execute(sql).fetchall()
    out = [dict(r) for r in rows]
    for r in out:
        r.pop("rk", None)
    return out


def inbox_set_fit(inbox_id: int, fit: int, why: str, source: str = "manual"):
    """Set an inbox row's fit + why. Snapshots the prior fit/score to
    score_history BEFORE the UPDATE (mirrors the status_history precedent), so
    a re-rank can be undone and before/after diffed. `source` tags the change
    ('manual', 'file_import', ...)."""
    from datetime import datetime, timezone
    def _job_key_of(row) -> str:
        try:
            from models import JobResult
            j = JobResult(title=row["title"], company=row["company"],
                          location=row["location"], salary_min=None, salary_max=None,
                          description="", url=row["url"] or "", source_keyword="",
                          created="", source_api=row["source"] or "")
            # job_key when WS-1 has landed it; else the existing identity_key.
            # Never AttributeError on today's models.py (job_key not present yet).
            return getattr(j, "job_key", None) or j.identity_key
        except Exception:
            return ""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT title, company, location, url, source, fit, score "
            "FROM inbox WHERE id=?", (inbox_id,)).fetchone()
        if row is not None:
            conn.execute(
                "INSERT INTO score_history "
                "(inbox_id, job_key, old_fit, new_fit, old_score, source, ts) "
                "VALUES (?,?,?,?,?,?,?)",
                (inbox_id, _job_key_of(row), row["fit"], fit, row["score"],
                 source, datetime.now(timezone.utc).replace(microsecond=0).isoformat()))
        conn.execute("UPDATE inbox SET fit=?, fit_why=? WHERE id=?",
                     (fit, why, inbox_id))
        conn.commit()


def inbox_set_extras(inbox_id: int, extras: str):
    """Write the round-trip extras JSON blob (new_rank/tags/...) onto an inbox
    row. No history row (extras are additive context, not a scored change)."""
    with get_conn() as conn:
        conn.execute("UPDATE inbox SET extras=? WHERE id=?", (extras or "", inbox_id))
        conn.commit()


def inbox_merge_extras(inbox_id: int, patch: dict):
    """Merge keys into an inbox row's extras JSON, preserving keys not in
    `patch` (so a rank-only write keeps an existing `tags`). Tolerant of a
    missing or non-dict current blob (treated as {})."""
    import json
    with get_conn() as conn:
        row = conn.execute("SELECT extras FROM inbox WHERE id=?",
                           (inbox_id,)).fetchone()
        current = {}
        if row and row["extras"]:
            try:
                loaded = json.loads(row["extras"])
                if isinstance(loaded, dict):
                    current = loaded
            except (ValueError, TypeError):
                current = {}
        current.update(patch)
        conn.execute("UPDATE inbox SET extras=? WHERE id=?",
                     (json.dumps(current), inbox_id))
        conn.commit()


def inbox_undo_last_rerank(scope: str) -> int:
    """Revert the most recent re-rank batch: restore each inbox row's fit to the
    old_fit recorded in the newest score_history timestamp group for `scope`
    ('any' = ignore source). Deletes the reverted history rows. Returns rows
    restored."""
    with get_conn() as conn:
        if scope == "any":
            row = conn.execute("SELECT MAX(ts) AS ts FROM score_history").fetchone()
        else:
            row = conn.execute(
                "SELECT MAX(ts) AS ts FROM score_history WHERE source=?",
                (scope,)).fetchone()
        last_ts = row["ts"] if row else None
        if not last_ts:
            return 0
        if scope == "any":
            hist = conn.execute(
                "SELECT id, inbox_id, old_fit FROM score_history WHERE ts=?",
                (last_ts,)).fetchall()
        else:
            hist = conn.execute(
                "SELECT id, inbox_id, old_fit FROM score_history "
                "WHERE ts=? AND source=?", (last_ts, scope)).fetchall()
        restored = 0
        for h in hist:
            conn.execute("UPDATE inbox SET fit=? WHERE id=?",
                         (h["old_fit"], h["inbox_id"]))
            conn.execute("DELETE FROM score_history WHERE id=?", (h["id"],))
            restored += 1
        conn.commit()
        return restored


def inbox_count() -> int:
    with get_conn() as conn:
        return conn.execute("SELECT COUNT(*) FROM inbox").fetchone()[0]


def inbox_company_counts() -> dict[str, int]:
    """Persisted inbox rows per company, keyed by lowercased/stripped company so
    the per-company cap can be enforced against what's ALREADY in the inbox (not
    just this run's batch). Empty company names are ignored."""
    counts: dict[str, int] = {}
    with get_conn() as conn:
        for r in conn.execute("SELECT company FROM inbox"):
            key = (r["company"] or "").lower().strip()
            if key:
                counts[key] = counts.get(key, 0) + 1
    return counts


def inbox_delete(inbox_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM inbox WHERE id=?", (inbox_id,))
        conn.commit()


def inbox_delete_urls(urls) -> int:
    """Delete inbox rows by exact url (used by the 'Clean dead links' action so it
    removes the rows a prune dry-run already identified, without re-probing the
    network). Returns the number of rows removed."""
    n = 0
    with get_conn() as conn:
        for u in urls:
            if u:
                n += conn.execute("DELETE FROM inbox WHERE url=?", (u,)).rowcount
        conn.commit()
    return n


def inbox_track(inbox_id: int) -> int | None:
    """Promote an inbox row to a tracked application (status=interested).
    Returns the new application id, or None if the row vanished."""
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM inbox WHERE id=?", (inbox_id,)).fetchone()
    if row is None:
        return None
    app_id = add_job(
        title=row["title"], company=row["company"], location=row["location"],
        url=row["url"], salary_text=row["salary_text"], source=row["source"],
        status="interested", description=row["description"], score=row["score"],
        fit_score=row["fit"], fit_rationale=row["fit_why"],
    )
    inbox_delete(inbox_id)
    return app_id


def inbox_dismiss(inbox_id: int):
    """Dismiss an inbox row: hidden from all future searches and daily runs."""
    with get_conn() as conn:
        row = conn.execute("SELECT url FROM inbox WHERE id=?", (inbox_id,)).fetchone()
    if row:
        dismiss_url(row["url"])
    inbox_delete(inbox_id)


# ── Run health beacon ─────────────────────────────────────────────────────────

def record_run_start(project: str | None = None) -> int:
    """Open a 'running' row for a daily_run and return its id. Pair with
    record_run_finish (success path) or the top-level except handler (failure)."""
    from datetime import datetime, timezone
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO runs (project, started_at, status) VALUES (?,?,'running')",
            (project or "", datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        return cur.lastrowid


def record_run_finish(run_id: int, status: str, source_counts=None, error: str = ""):
    """Close a run row: status in {'ok','zero','failed'}, per-source counts (any
    JSON-able mapping) and an optional error/traceback for the failed path."""
    import json
    from datetime import datetime, timezone
    counts_json = json.dumps(source_counts) if source_counts is not None else ""
    with get_conn() as conn:
        conn.execute(
            "UPDATE runs SET finished_at=?, status=?, source_counts=?, error=? "
            "WHERE id=?",
            (datetime.now(timezone.utc).isoformat(), status, counts_json,
             error or "", run_id),
        )
        conn.commit()


def get_last_run(project: str | None = None) -> dict | None:
    """Most recent run row (overall, or for one project when given) as a dict, or
    None if there are no runs yet. Signature is read by the GUI's last-run badge."""
    with get_conn() as conn:
        if project is not None:
            row = conn.execute(
                "SELECT * FROM runs WHERE project=? ORDER BY id DESC LIMIT 1",
                (project,),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM runs ORDER BY id DESC LIMIT 1"
            ).fetchone()
    return dict(row) if row else None
