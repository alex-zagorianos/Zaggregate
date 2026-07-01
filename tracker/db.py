import atexit
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
# v5 (2026-07-01 storage research): applications.norm_url (+ index) and the
# inbox_fts FTS5 search index are new schema objects, so DBs already at v4 must
# re-run the migration to pick them up.
SCHEMA_VERSION = 5


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


# Bounded mmap window for read-heavy GUI queries (phiresky's SQLite tuning
# benchmark - see brain/research-2026-07-01-reach-storage.md). 256 MiB is well
# above any realistic per-project tracker.db size, so this is a ceiling, not a
# working assumption; SQLite falls back to normal I/O beyond it.
_MMAP_SIZE = 256 * 1024 * 1024


def get_conn():
    # The headless daily_run and the GUI write the same project DB. WAL lets
    # reads proceed during a write, and busy_timeout waits out brief lock
    # contention instead of raising 'database is locked'.
    conn = sqlite3.connect(str(current_db_path()), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA journal_mode=WAL")
    # synchronous=NORMAL is the documented-safe pairing with WAL (sqlite.org/
    # wal.html): durable against an app crash, only the last transaction is at
    # risk on an OS crash/power loss - a worthwhile write-throughput win for
    # inbox_add_many's per-run batch inserts.
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute(f"PRAGMA mmap_size={_MMAP_SIZE}")
    return conn


def checkpoint() -> None:
    """Best-effort WAL checkpoint (TRUNCATE) so the -wal sidecar doesn't grow
    unbounded, plus PRAGMA optimize (SQLite's own recommended pre-close
    housekeeping). Guarded to NEVER raise - safe to call from atexit, the GUI's
    window-close handler, or anywhere else on a clean-shutdown path. No-ops
    (and never creates a db file) when there's nothing to checkpoint."""
    try:
        path = current_db_path()
        if not Path(path).exists():
            return
        conn = sqlite3.connect(str(path), timeout=2)
        try:
            conn.execute("PRAGMA busy_timeout=2000")
            # optimize can itself write (refreshed planner stats) - run it
            # BEFORE the truncate checkpoint, else its write would regrow the
            # -wal file we just shrank.
            conn.execute("PRAGMA optimize")
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        finally:
            conn.close()
    except Exception:
        pass


def close_db() -> None:
    """Explicit clean-shutdown hook (GUI window close, CLI exit) - alias for
    checkpoint(). Safe to call multiple times."""
    checkpoint()


# Run on clean process exit so a normal quit doesn't leave a growing -wal
# sidecar behind. checkpoint() is fully guarded (never raises), so this can't
# turn a clean exit into a crash.
atexit.register(checkpoint)


def _existing_columns(conn) -> set[str]:
    return {r["name"] for r in conn.execute("PRAGMA table_info(applications)")}


def _safe_add_column(conn, table: str, col: str, decl: str) -> None:
    """ALTER ADD COLUMN that tolerates a concurrent first-init race: if another
    process added the column between our PRAGMA probe and here, SQLite raises
    'duplicate column name' - swallow exactly that and re-raise anything else."""
    import sqlite3
    try:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")
    except sqlite3.OperationalError as e:
        if "duplicate column name" not in str(e).lower():
            raise


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
                # Flush the WAL into the main db first, else copy2 of the bare
                # .db file can miss committed-but-not-checkpointed data.
                try:
                    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                except Exception:
                    pass
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
                _safe_add_column(conn, "applications", col, decl)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_status ON applications(status)")
        # v5 (STORAGE item 3): norm_url mirrors inbox's dedup-key pattern so
        # tracked-URL lookups can use an indexed exact match instead of
        # normalizing every row in Python on every call (tracked_urls()).
        # applications.url itself also gets an index - some callers still look
        # it up by the raw URL.
        if "norm_url" not in existing:
            _safe_add_column(conn, "applications", "norm_url", "TEXT DEFAULT ''")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_applications_url ON applications(url)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_applications_norm_url ON applications(norm_url)")
        # Backfill norm_url for rows that predate this column (normalize_url is
        # a Python function, so this can't be a pure-SQL UPDATE).
        for r in conn.execute(
            "SELECT id, url FROM applications WHERE (norm_url IS NULL OR norm_url='') "
            "AND url != ''"
        ).fetchall():
            conn.execute("UPDATE applications SET norm_url=? WHERE id=?",
                         (normalize_url(r["url"]), r["id"]))
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
                _safe_add_column(conn, "inbox", col, decl)
        # Round-robin window orders by company; without this index every render
        # does a full partition sort over the whole inbox.
        conn.execute("CREATE INDEX IF NOT EXISTS idx_inbox_company ON inbox(company)")
        # inbox.url is looked up by exact match (inbox_delete_urls' prune path);
        # norm_url already gets an implicit index from its UNIQUE constraint.
        conn.execute("CREATE INDEX IF NOT EXISTS idx_inbox_url ON inbox(url)")
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
            _safe_add_column(conn, "inbox", "extras", "TEXT DEFAULT ''")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS score_history (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                inbox_id  INTEGER NOT NULL,
                job_key   TEXT DEFAULT '',
                old_fit   INTEGER,
                new_fit   INTEGER,
                old_score INTEGER,
                source    TEXT DEFAULT '',
                batch     TEXT DEFAULT '',
                ts        TEXT NOT NULL
            )
        """)
        _safe_add_column(conn, "score_history", "batch", "TEXT DEFAULT ''")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_score_history_inbox "
                     "ON score_history(inbox_id)")
        # v4 (TASK C): lightweight local contacts/referral CRM — the networking
        # gap. Manual capture only (no scraping). app_id optionally links a
        # contact back to a tracked application.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS contacts (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                name           TEXT NOT NULL,
                role           TEXT DEFAULT '',
                email          TEXT DEFAULT '',
                linkedin       TEXT DEFAULT '',
                company        TEXT DEFAULT '',
                app_id         INTEGER,
                last_contacted TEXT DEFAULT '',
                note           TEXT DEFAULT '',
                created        TEXT NOT NULL
            )
        """)
        # v5 (STORAGE item 2): external-content FTS5 index over inbox so an
        # already-triaged posting can be found again (title/company/location/
        # description) - closes a real usability gap as the inbox grows.
        # External-content ('content=inbox') keeps the JD text from being
        # stored twice. Guarded: some SQLite builds omit FTS5 entirely -
        # inbox_search() falls back to a LIKE scan when this vtable is absent,
        # so a missing module here never crashes the app.
        try:
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS inbox_fts USING fts5(
                    title, company, location, description,
                    content='inbox', content_rowid='id'
                )
            """)
            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS inbox_fts_ai AFTER INSERT ON inbox BEGIN
                    INSERT INTO inbox_fts(rowid, title, company, location, description)
                    VALUES (new.id, new.title, new.company, new.location, new.description);
                END
            """)
            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS inbox_fts_ad AFTER DELETE ON inbox BEGIN
                    INSERT INTO inbox_fts(inbox_fts, rowid, title, company, location, description)
                    VALUES ('delete', old.id, old.title, old.company, old.location, old.description);
                END
            """)
            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS inbox_fts_au AFTER UPDATE ON inbox BEGIN
                    INSERT INTO inbox_fts(inbox_fts, rowid, title, company, location, description)
                    VALUES ('delete', old.id, old.title, old.company, old.location, old.description);
                    INSERT INTO inbox_fts(rowid, title, company, location, description)
                    VALUES (new.id, new.title, new.company, new.location, new.description);
                END
            """)
            # Backfill rows that predate the index. Unconditional (not gated on
            # an emptiness check): for an external-content table, a plain
            # `SELECT COUNT(*) FROM inbox_fts` reads through to the *content*
            # table (inbox) rather than the FTS b-tree, so it can't tell us
            # whether rows are actually indexed - and re-inserting an
            # already-indexed rowid is a verified no-op (SQLite dedupes on
            # rowid), so running this every time the migration body executes
            # is safe. In practice it only executes once per DB anyway (this
            # whole block is gated by init_db's user_version fast path).
            conn.execute("""
                INSERT INTO inbox_fts(rowid, title, company, location, description)
                SELECT id, title, company, location, description FROM inbox
            """)
        except sqlite3.OperationalError:
            pass  # FTS5 not compiled into this SQLite build
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
        job_id = cur.lastrowid
        if url:
            # Populate the indexed dedup key (STORAGE item 3) so tracked-URL
            # lookups/anti-joins don't need to re-normalize every row in
            # Python. Tolerant of a not-yet-migrated DB (pre-norm_url schema)
            # so this never turns into a new failure mode for callers that
            # insert before init_db() has run.
            try:
                conn.execute("UPDATE applications SET norm_url=? WHERE id=?",
                             (normalize_url(url), job_id))
            except sqlite3.OperationalError:
                pass
        conn.commit()
        return job_id


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
        if "url" in updates:
            # Keep the indexed dedup key (STORAGE item 3) in sync whenever a
            # user edits an application's URL, so it doesn't go stale and
            # break urls_not_seen()'s anti-join. Tolerant of a not-yet-
            # migrated DB, same as add_job().
            try:
                conn.execute("UPDATE applications SET norm_url=? WHERE id=?",
                             (normalize_url(updates["url"]), job_id))
            except sqlite3.OperationalError:
                pass
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


# ── Contacts / referral CRM (manual capture — the networking gap) ─────────────

def add_contact(name, role="", email="", linkedin="", company="", app_id=None,
                last_contacted="", note="") -> int:
    """Record a networking contact. app_id optionally ties the contact to a
    tracked application. Returns the new contact id."""
    from datetime import datetime, timezone
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO contacts "
            "(name, role, email, linkedin, company, app_id, last_contacted, "
            "note, created) VALUES (?,?,?,?,?,?,?,?,?)",
            (name, role, email, linkedin, company, app_id, last_contacted, note,
             datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        return cur.lastrowid


def list_contacts() -> list[dict]:
    """All contacts, newest first."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM contacts ORDER BY id DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def contacts_for_company(company) -> list[dict]:
    """Contacts at a given company (case-insensitive match), newest first."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM contacts WHERE LOWER(company)=LOWER(?) ORDER BY id DESC",
            (company or "",),
        ).fetchall()
    return [dict(r) for r in rows]


def delete_contact(contact_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM contacts WHERE id=?", (contact_id,))
        conn.commit()


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


def urls_not_seen(norm_urls) -> set[str]:
    """STORAGE item 3: given a batch of already-normalized candidate URLs,
    return the subset that is neither tracked (applications) nor dismissed -
    via an indexed SQL anti-join (NOT EXISTS) instead of materializing the
    full tracked+dismissed URL sets in Python the way seen_urls() does.
    Equivalent to `{u for u in norm_urls if u not in seen_urls()}`, but scales
    with the candidate batch (one search run's worth of results) rather than
    with the applications/dismissed table size, so it stays cheap as those
    tables grow past a few thousand rows. Uses applications.norm_url (indexed,
    STORAGE item 3) and dismissed.url (already-normalized, PK-indexed)."""
    candidates = [u for u in dict.fromkeys(norm_urls) if u]
    if not candidates:
        return set()
    # Chunk the candidate batch: one bind parameter per URL, so an unbounded batch
    # can exceed SQLite's compiled MAX_VARIABLE_NUMBER (999 on old builds) and raise.
    # 500/batch stays well under even the legacy cap; results union across batches.
    out: set[str] = set()
    with get_conn() as conn:
        for i in range(0, len(candidates), 500):
            batch = candidates[i:i + 500]
            values_sql = ",".join("(?)" for _ in batch)
            rows = conn.execute(
                f"WITH candidates(norm_url) AS (VALUES {values_sql}) "
                "SELECT c.norm_url FROM candidates c "
                "WHERE NOT EXISTS "
                "(SELECT 1 FROM applications a WHERE a.norm_url = c.norm_url) "
                "AND NOT EXISTS "
                "(SELECT 1 FROM dismissed d WHERE d.url = c.norm_url)",
                batch,
            ).fetchall()
            out.update(r[0] for r in rows)
    return out


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
    # STORAGE item 3: bounded SQL anti-join over just this batch's candidate
    # URLs, instead of materializing the full tracked+dismissed URL sets
    # (seen_urls()) in Python - semantically identical skip decision, but
    # scales with the batch, not with the applications/dismissed table size.
    norm_by_job = [(j, normalize_url(j.url)) for j in jobs]
    unseen = urls_not_seen([n for _, n in norm_by_job if n])
    today = date.today().isoformat()
    # Start the running tally from what's already persisted so the cap spans runs.
    per_company = inbox_company_counts() if per_company_cap > 0 else {}
    added = 0
    with get_conn() as conn:
        for j, norm in norm_by_job:
            if not norm or norm not in unseen:
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
                # Per-job extras: a transient `_extras` dict on the JobResult
                # (e.g. browser-harvest "browse" metadata) plus the freshness
                # stamp share the row's extras JSON. Both schema-free.
                extra = dict(getattr(j, "_extras", None) or {})
                if new_batch and getattr(j, "is_new", False):
                    extra["new_batch"] = new_batch
                # schema.org validThrough (publisher-attested expiry) rides the
                # extras JSON so match.ghost's strongest stale signal fires in the
                # live GUI (which reads inbox rows, not JobResults). Schema-free.
                if getattr(j, "valid_through", ""):
                    extra["valid_through"] = j.valid_through
                if extra:
                    conn.execute("UPDATE inbox SET extras=? WHERE id=?",
                                 (json.dumps(extra), cur.lastrowid))
                if per_company_cap > 0:
                    per_company[key] = per_company.get(key, 0) + 1
            added += cur.rowcount
        if added:
            _fts_optimize(conn)
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


# ── Full-text search over the inbox (STORAGE item 2) ───────────────────────────

def _inbox_fts_ready(conn) -> bool:
    """True if THIS db has a working inbox_fts vtable: FTS5 compiled into the
    SQLite build AND init_db() successfully created it. A cheap sqlite_master
    lookup rather than a process-global cache, since it's correct per-db (a
    fresh in-memory test db never shares state with another)."""
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='inbox_fts'"
    ).fetchone()
    return row is not None


def _fts5_match_query(text: str) -> str:
    """Turn free-text user input into a safe FTS5 MATCH expression: each
    whitespace-separated token becomes its own quoted phrase (AND'd together
    implicitly), so characters FTS5 treats as query syntax (-, *, :, parens,
    unterminated quotes, ...) can never raise a MATCH syntax error."""
    return " ".join('"' + tok.replace('"', '""') + '"' for tok in text.split())


def _fts_optimize(conn) -> None:
    """Merge FTS5 b-tree segments after a bulk inbox write (import/prune) -
    batched housekeeping done once per call, not per row. No-op if the FTS5
    vtable isn't present (unsupported SQLite build, or not yet created)."""
    try:
        conn.execute("INSERT INTO inbox_fts(inbox_fts) VALUES('optimize')")
    except sqlite3.OperationalError:
        pass


def inbox_search(query: str) -> list[dict]:
    """Full-text search over inbox(title, company, location, description),
    ranked by relevance - so an already-triaged posting can be found again as
    the inbox grows (there's otherwise no local search over what's already
    been saved). Uses FTS5 MATCH when the SQLite build/db supports it;
    degrades to a LIKE substring scan otherwise - or if the MATCH query itself
    errors - so the app never crashes on an FTS5-less build. Returns full
    inbox rows (not just the indexed columns), most-relevant first."""
    query = (query or "").strip()
    if not query:
        return []
    with get_conn() as conn:
        if _inbox_fts_ready(conn):
            try:
                rows = conn.execute(
                    "SELECT inbox.* FROM inbox_fts "
                    "JOIN inbox ON inbox.id = inbox_fts.rowid "
                    "WHERE inbox_fts MATCH ? ORDER BY inbox_fts.rank "
                    "LIMIT 200",
                    (_fts5_match_query(query),),
                ).fetchall()
                return [dict(r) for r in rows]
            except sqlite3.OperationalError:
                pass  # bad MATCH expression or a stale/broken vtable - fall through
        like = f"%{query}%"
        rows = conn.execute(
            "SELECT * FROM inbox WHERE title LIKE ? OR company LIKE ? "
            "OR location LIKE ? OR description LIKE ? "
            "ORDER BY COALESCE(NULLIF(created,''), date_added) DESC "
            "LIMIT 200",
            (like, like, like, like),
        ).fetchall()
        return [dict(r) for r in rows]


def inbox_set_fit(inbox_id: int, fit: int, why: str, source: str = "manual",
                  batch: str = "") -> bool:
    """Set an inbox row's fit + why. Snapshots the prior fit/score to
    score_history BEFORE the UPDATE (mirrors the status_history precedent), so
    a re-rank can be undone and before/after diffed. `source` tags the change
    ('manual', 'file_import', 'bridge', 'api', 'mcp', 'gate', ...).

    Returns True when a row was actually updated, False on a missing/unknown id
    (previously a silent no-op) — so callers writing from arbitrary AIs can count
    only the scores that really landed, and no phantom score_history row is
    written for an id that does not exist."""
    from datetime import datetime, timezone
    # A batch groups one logical re-rank so undo reverts the whole set at once.
    # apply_rerank_scores passes one shared id; a direct/manual call gets its own
    # singleton batch so it's still individually undoable (never an empty batch,
    # which the batch-keyed undo would skip).
    if not batch:
        import uuid
        batch = uuid.uuid4().hex[:12]
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
        if row is None:
            # Unknown id: no history row, no phantom "applied". (Fixes the
            # MCP set_fit_scores counting nonexistent ids as applied.)
            return False
        conn.execute(
            "INSERT INTO score_history "
            "(inbox_id, job_key, old_fit, new_fit, old_score, source, batch, ts) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (inbox_id, _job_key_of(row), row["fit"], fit, row["score"],
             source, batch,
             datetime.now(timezone.utc).replace(microsecond=0).isoformat()))
        conn.execute("UPDATE inbox SET fit=?, fit_why=? WHERE id=?",
                     (fit, why, inbox_id))
        conn.commit()
        return True


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
                     (json.dumps(current, separators=(",", ":")), inbox_id))
        conn.commit()


def inbox_undo_last_rerank(scope: str) -> int:
    """Revert the most recent re-rank BATCH: restore each inbox row's fit to the
    old_fit recorded for the newest score_history `batch` matching `scope`
    ('any' = ignore source). Also strips rank/rec_batch from those rows' extras so
    Top Picks drops the undone shortlist. Deletes the reverted history rows.
    Returns rows restored."""
    import json
    with get_conn() as conn:
        if scope == "any":
            row = conn.execute(
                "SELECT batch FROM score_history WHERE batch != '' "
                "ORDER BY ts DESC, id DESC LIMIT 1").fetchone()
        else:
            row = conn.execute(
                "SELECT batch FROM score_history WHERE batch != '' AND source=? "
                "ORDER BY ts DESC, id DESC LIMIT 1", (scope,)).fetchone()
        last_batch = row["batch"] if row else None
        if not last_batch:
            return 0
        if scope == "any":
            hist = conn.execute(
                "SELECT id, inbox_id, old_fit FROM score_history WHERE batch=?",
                (last_batch,)).fetchall()
        else:
            hist = conn.execute(
                "SELECT id, inbox_id, old_fit FROM score_history "
                "WHERE batch=? AND source=?", (last_batch, scope)).fetchall()
        restored = 0
        for h in hist:
            conn.execute("UPDATE inbox SET fit=? WHERE id=?",
                         (h["old_fit"], h["inbox_id"]))
            # F23: drop the shortlist keys so top_picks() no longer surfaces this batch.
            erow = conn.execute("SELECT extras FROM inbox WHERE id=?",
                                (h["inbox_id"],)).fetchone()
            if erow and erow["extras"]:
                try:
                    blob = json.loads(erow["extras"])
                except (ValueError, TypeError):
                    blob = None
                if isinstance(blob, dict):
                    blob.pop("rank", None)
                    blob.pop("rec_batch", None)
                    conn.execute("UPDATE inbox SET extras=? WHERE id=?",
                                 (json.dumps(blob), h["inbox_id"]))
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


def inbox_company_display_names() -> dict[str, str]:
    """Map a lowercased/stripped company key -> a representative ORIGINAL-CASED
    company name from the inbox (first non-empty spelling seen). Lets callers
    recover a proper display name for a key returned by inbox_company_counts(),
    which lowercases its keys."""
    names: dict[str, str] = {}
    with get_conn() as conn:
        for r in conn.execute("SELECT company FROM inbox"):
            raw = (r["company"] or "").strip()
            key = raw.lower()
            if key and key not in names:
                names[key] = raw
    return names


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
        if n:
            _fts_optimize(conn)
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
