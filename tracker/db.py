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
# v6 (C1 dedup): inbox.job_key (+ index) - WS-1's stable cross-source identity,
# persisted per row so inbox_add_many can coalesce the SAME posting surfaced by
# two overlap sources under different URLs. Old rows backfill NULL (their JobResult
# is gone and job_key can't be reliably recomputed from a stored row), and the
# dedup logic treats NULL as "no key" (never coalesces on it).
# v7 (D1 application-cycle): new interview_rounds table; status_history.note
# column (per-stage timestamped notes + note-only events); applications offer_*
# columns via the _EXTRA_COLUMNS ALTER pattern. All additive/backfill-free.
SCHEMA_VERSION = 7


def current_db_path() -> Path:
    return Path(DB_PATH) if DB_PATH is not None else workspace.db_path()

STATUSES = ["interested", "applied", "phone_screen", "interview", "offer",
            "accepted", "rejected", "withdrawn", "ghosted"]
STATUS_LABELS = {
    "interested":  "Interested",
    "applied":     "Applied",
    "phone_screen":"Phone Screen",
    "interview":   "Interview",
    "offer":       "Offer",
    "accepted":    "Accepted",     # success terminal — you got (and took) the job
    "rejected":    "Rejected",
    "withdrawn":   "Withdrawn",
    "ghosted":     "Ghosted",      # terminal — the employer went silent
}

# Applications with no status_history movement in this many days while still at
# 'applied' are treated as candidates for the auto-ghost nudge. Config-free
# constant (D1 P5): 3 weeks with no response is the practical give-up signal.
GHOST_NUDGE_DAYS = 21

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
    # Offer fields (D1 P5): shown in JobDialog once a role reaches offer/accepted,
    # so offer->accepted yield is reportable.
    "offer_amount":   "TEXT DEFAULT ''",     # offered comp (free text: '$120k', '$58/hr')
    "offer_deadline": "TEXT DEFAULT ''",     # decision deadline (YYYY-MM-DD)
    "offer_notes":    "TEXT DEFAULT ''",     # negotiation notes / verbal terms
}

_EDITABLE = {
    "status", "notes", "date_applied", "title", "company", "location", "url",
    "salary_text", "follow_up_date", "deadline", "contact", "description", "resume_path",
    "cover_path", "score", "fit_score", "fit_rationale",
    "offer_amount", "offer_deadline", "offer_notes",
}


class UnknownFieldError(ValueError):
    """A tracker update was passed a field name that isn't an editable column.

    Raised (instead of silently dropping the field) so a scripted/BYO-AI caller
    that guesses a wrong column name — e.g. 'offer_salary' for the real
    'offer_amount' — gets a hard, actionable error rather than losing the value
    with no signal (S32/L3). Subclasses ValueError so existing `except ValueError`
    handlers still catch it.
    """


def _reject_unknown_fields(fn_name: str, fields: dict, allowed: set) -> None:
    """Raise UnknownFieldError if `fields` contains any key outside `allowed`.

    An empty `fields` dict is fine (that's a caller-side no-op, handled by the
    `if not updates` guard downstream) — this only fires when the caller DID
    supply something and at least one supplied key is not an editable column.
    The message lists the offending keys and the closest valid alternatives so
    a wrong-column guess ('offer_salary') points the caller at 'offer_amount'.
    """
    unknown = [k for k in fields if k not in allowed]
    if not unknown:
        return
    import difflib
    hints = []
    for k in unknown:
        near = difflib.get_close_matches(k, sorted(allowed), n=1, cutoff=0.6)
        hints.append(f"{k!r}" + (f" (did you mean {near[0]!r}?)" if near else ""))
    raise UnknownFieldError(
        f"{fn_name}: unknown field(s) {', '.join(hints)}. "
        f"Editable fields: {', '.join(sorted(allowed))}."
    )


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
        # board_count: post-original column. job_key (v6, C1): NO default - old
        # rows must read NULL, not '', so cross-source coalescing can tell "no key
        # recorded" (skip) from a real empty-string key. Never backfilled: a stored
        # inbox row has lost its JobResult and job_key can't be recomputed reliably.
        for col, decl in {"board_count": "INTEGER DEFAULT -1",
                          "job_key": "TEXT"}.items():
            if col not in inbox_existing:
                _safe_add_column(conn, "inbox", col, decl)
        # Round-robin window orders by company; without this index every render
        # does a full partition sort over the whole inbox.
        conn.execute("CREATE INDEX IF NOT EXISTS idx_inbox_company ON inbox(company)")
        # inbox.url is looked up by exact match (inbox_delete_urls' prune path);
        # norm_url already gets an implicit index from its UNIQUE constraint.
        conn.execute("CREATE INDEX IF NOT EXISTS idx_inbox_url ON inbox(url)")
        # job_key coalescing (v6, C1) does an existence probe per candidate; index
        # it so the anti-join stays cheap as the inbox grows.
        conn.execute("CREATE INDEX IF NOT EXISTS idx_inbox_job_key ON inbox(job_key)")
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
        # v7 (D1): per-stage timestamped notes. A note-only event has
        # old_status == new_status and a non-empty note; a real transition may
        # also carry a note. Added via the same in-place pattern so an existing
        # status_history table upgrades without data loss.
        sh_existing = {r["name"] for r in conn.execute(
            "PRAGMA table_info(status_history)")}
        if "note" not in sh_existing:
            _safe_add_column(conn, "status_history", "note", "TEXT DEFAULT ''")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_status_history_job "
                     "ON status_history(job_id)")
        # v7 (D1): interview rounds — one row per scheduled/completed interview so
        # the full application cycle (phone/tech/onsite/final) is trackable and
        # each round can be exported to a .ics calendar event.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS interview_rounds (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                app_id       INTEGER NOT NULL,
                round_no     INTEGER DEFAULT 0,
                kind         TEXT DEFAULT 'other',
                scheduled_at TEXT DEFAULT '',
                interviewer  TEXT DEFAULT '',
                notes        TEXT DEFAULT '',
                outcome      TEXT DEFAULT ''
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_interview_rounds_app "
                     "ON interview_rounds(app_id)")
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


# ── Data safety (D1 P5): integrity check + rolling daily backup ───────────────

def quick_check() -> tuple[bool, str]:
    """Run PRAGMA quick_check once (called at launch). Returns (ok, message):
    ok=True when the db is fine ('ok') or doesn't exist yet (nothing to check);
    ok=False with the first reported problem otherwise. Fully guarded — never
    raises, so a failed check surfaces as a warning, never a crash."""
    try:
        path = current_db_path()
        if not Path(path).exists():
            return True, "ok"
        conn = sqlite3.connect(str(path), timeout=5)
        try:
            rows = conn.execute("PRAGMA quick_check").fetchall()
        finally:
            conn.close()
        results = [str(r[0]) for r in rows]
        if results == ["ok"]:
            return True, "ok"
        return False, "; ".join(results[:5])
    except Exception as e:  # noqa: BLE001 - integrity check must never crash launch
        return False, f"quick_check failed: {e}"


def rolling_backup(keep: int = 7, today=None) -> Path | None:
    """Once per day (first open), snapshot tracker.db to a dated backup next to
    it, keeping the last `keep` snapshots. Reuses the migration-backup pattern:
    WAL-checkpoint (so the copy includes committed-but-un-checkpointed data) then
    shutil.copy2. Returns the backup path written, or None when nothing was
    written (db missing, or today's snapshot already exists). Best-effort — never
    raises."""
    import shutil
    from datetime import date
    try:
        src = Path(current_db_path())
        if not src.exists():
            return None
        stamp = (today or date.today().isoformat())
        dest = src.with_name(src.name + f".bak-{stamp}")
        if dest.exists():
            return None  # already backed up today
        try:
            conn = sqlite3.connect(str(src), timeout=5)
            try:
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            finally:
                conn.close()
        except Exception:
            pass  # checkpoint is best-effort; copy proceeds regardless
        shutil.copy2(str(src), str(dest))
        # Prune older dated snapshots, keeping the newest `keep`.
        prefix = src.name + ".bak-"
        snaps = sorted(
            (p for p in src.parent.glob(src.name + ".bak-*")
             if _is_dated_backup(p.name, prefix)),
            key=lambda p: p.name)
        for old in snaps[:-keep] if keep > 0 else []:
            try:
                old.unlink()
            except OSError:
                pass
        return dest
    except Exception:
        return None


def _is_dated_backup(name: str, prefix: str) -> bool:
    """True for a '<db>.bak-YYYY-MM-DD' snapshot (not the '.bak-vN' migration
    backups, which must not be pruned by the rolling-backup rotation)."""
    if not name.startswith(prefix):
        return False
    tail = name[len(prefix):]
    return len(tail) == 10 and tail[4] == "-" and tail[7] == "-" and \
        tail.replace("-", "").isdigit()


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


def count_followups_due(today=None, include_no_response=True):
    """Number of active (non-archived) applications needing attention — for the
    Tracker header nudge, the tab badge, and the startup banner. Counts every row
    whose follow_up_date has arrived, PLUS (when include_no_response, D1 P5) the
    auto-ghost 'no response' candidates that aren't already counted by their
    follow-up date. A targeted COUNT so the GUI no longer pulls the whole table
    into Python just to tally this (GUI-10)."""
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
    n = int(row[0])
    if include_no_response:
        # Only count no-response rows NOT already surfaced by a due follow-up,
        # so the badge doesn't double-count one application.
        for r in stale_applications(today=today):
            fu = (r.get("follow_up_date") or "").strip()
            if not (fu and fu <= today):
                n += 1
    return n


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


def stale_applications(days=None, today=None):
    """Applications still at status 'applied' with NO status_history movement
    (any row newer than `days` days ago) — the auto-ghost candidates surfaced in
    the Due dialog as 'no response'. Modeled on followups_due: returns full row
    dicts, each stamped due_kind='no response' and due_date=<the reference date
    N days ago> (soonest/most-overdue first).

    "No movement" means: the most recent status_history.changed_at for the job is
    older than the cutoff (or there's no history at all and it was added before
    the cutoff). date_added is the fallback when history is missing so a freshly
    imported 'applied' row without a transition log still ages in.
    """
    from datetime import date, timedelta
    if days is None:
        days = GHOST_NUDGE_DAYS
    if today is None:
        today = date.today()
    elif isinstance(today, str):
        today = date.fromisoformat(today)
    cutoff = (today - timedelta(days=days)).isoformat()
    out = []
    with get_conn() as conn:
        for r in conn.execute(
            "SELECT * FROM applications WHERE archived=0 AND status='applied' "
            "ORDER BY id"
        ).fetchall():
            # Most recent history timestamp for this job (transition or note).
            last = conn.execute(
                "SELECT MAX(changed_at) FROM status_history WHERE job_id=?",
                (r["id"],),
            ).fetchone()[0]
            # Fall back to date_applied then date_added when there's no history.
            ref = last or (r["date_applied"] or "") or (r["date_added"] or "")
            if not ref:
                continue
            # Compare on the date portion so a bare date and an ISO timestamp both
            # work (changed_at is a full UTC timestamp; date_added is a bare date).
            if ref[:10] <= cutoff:
                d = dict(r)
                d["due_kind"], d["due_date"] = "no response", cutoff
                out.append(d)
    out.sort(key=lambda d: (d["due_date"], d.get("date_applied") or "", d["id"]))
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
    from datetime import datetime, timezone, date, timedelta
    # Reject unknown field names LOUDLY instead of silently dropping them
    # (S32/L3): a scripted or BYO-AI caller that guesses a wrong column
    # ('offer_salary' vs the real 'offer_amount') would otherwise lose data with
    # no error, no warning, and a None return. Raise so the mistake surfaces at
    # the call site. Note: an empty call (no fields at all) stays a silent no-op
    # — that's "nothing to update", not "unknown field".
    _reject_unknown_fields("update_job", fields, _EDITABLE)
    updates = {k: v for k, v in fields.items() if k in _EDITABLE}
    if not updates:
        return
    with get_conn() as conn:
        # Record a status transition (old->new) before applying it, so the
        # status_history funnel reflects every real change. (delegate T4)
        if "status" in updates:
            row = conn.execute(
                "SELECT status, date_applied, follow_up_date FROM applications "
                "WHERE id=?", (job_id,)
            ).fetchone()
            if row and row["status"] != updates["status"]:
                conn.execute(
                    "INSERT INTO status_history "
                    "(job_id, old_status, new_status, changed_at) VALUES (?,?,?,?)",
                    (job_id, row["status"], updates["status"],
                     datetime.now(timezone.utc).isoformat()),
                )
                # Centralized entered-'applied' side-effects (D1 P5): stamp
                # date_applied if blank and arm a +7-day follow-up if blank, so
                # EVERY path into 'applied' (Apply Queue, Tracker quick-status,
                # Flask /update, /api/add, browser extension) arms the same
                # follow-up engine instead of only the Apply Queue button.
                # Only auto-fill when the caller didn't set the field itself.
                if updates["status"] == "applied":
                    today = date.today().isoformat()
                    if "date_applied" not in updates and not (row["date_applied"] or "").strip():
                        updates["date_applied"] = today
                    if "follow_up_date" not in updates and not (row["follow_up_date"] or "").strip():
                        updates["follow_up_date"] = (
                            date.today() + timedelta(days=7)).isoformat()
        set_clause = ", ".join(f"{k}=?" for k in updates)
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


# ── Per-stage notes + timeline (D1 P5) ────────────────────────────────────────

def add_status_note(job_id, note: str) -> int | None:
    """Attach a timestamped note to an application WITHOUT changing its status:
    a status_history event where old_status == new_status (the app's current
    status) carrying the note. Returns the new history-row id, or None if the
    application doesn't exist or the note is blank."""
    from datetime import datetime, timezone
    note = (note or "").strip()
    if not note:
        return None
    with get_conn() as conn:
        row = conn.execute(
            "SELECT status FROM applications WHERE id=?", (job_id,)
        ).fetchone()
        if row is None:
            return None
        cur = conn.execute(
            "INSERT INTO status_history "
            "(job_id, old_status, new_status, changed_at, note) VALUES (?,?,?,?,?)",
            (job_id, row["status"], row["status"],
             datetime.now(timezone.utc).isoformat(), note),
        )
        conn.commit()
        return cur.lastrowid


def status_timeline(job_id) -> list[dict]:
    """Chronological timeline for one application: every status_history row
    (transitions AND note-only events), oldest first, each a dict with
    old_status, new_status, changed_at, note and a 'kind' of 'status' (a real
    transition) or 'note' (old_status == new_status with a note). Read-only —
    for the job edit dialog's timeline pane."""
    out = []
    with get_conn() as conn:
        cols = {r["name"] for r in conn.execute(
            "PRAGMA table_info(status_history)")}
        has_note = "note" in cols
        sel = "old_status, new_status, changed_at" + (", note" if has_note else "")
        for r in conn.execute(
            f"SELECT {sel} FROM status_history WHERE job_id=? "
            "ORDER BY changed_at, id", (job_id,)
        ).fetchall():
            note = (r["note"] if has_note else "") or ""
            kind = "note" if (r["old_status"] == r["new_status"] and note) else "status"
            out.append({
                "old_status": r["old_status"], "new_status": r["new_status"],
                "changed_at": r["changed_at"], "note": note, "kind": kind,
            })
    return out


# ── Interview rounds (D1 P5) ──────────────────────────────────────────────────

# Round KIND -> the funnel STATUS it implies (S32/L4). The STATUS is the funnel
# source of truth (it drives analytics + the follow-up nudge, which keys off
# status only); a round is a scheduled event UNDER an interview-y status. Adding
# a round while the app is still pre-interview used to leave status at 'applied',
# so `count_followups_due`/`followups_due` never advanced — a user who logged
# their phone screen as a ROUND but left status at 'applied' got the wrong
# nudging. Adding a round now advances a pre-interview status to the stage the
# round implies, tying the two models together. A 'phone' round implies the
# 'phone_screen' stage; every other round kind implies 'interview'.
_ROUND_KIND_STATUS = {"phone": "phone_screen"}
_PRE_INTERVIEW_STATUSES = {"interested", "applied"}


def add_interview_round(app_id, kind="other", scheduled_at="", interviewer="",
                        notes="", outcome="", round_no=None) -> int:
    """Record an interview round for a tracked application. round_no defaults to
    the next sequential number for that app when not given. Returns the new id.

    Coherence (S32/L4): if the application is still at a pre-interview status
    (interested/applied), adding a round advances it to the stage the round kind
    implies (phone -> phone_screen, else interview) so the funnel + follow-up
    nudge stay consistent with the round having happened. A round on an already-
    interview-or-later status leaves the status untouched (never downgrades)."""
    with get_conn() as conn:
        if round_no is None:
            row = conn.execute(
                "SELECT COALESCE(MAX(round_no), 0) FROM interview_rounds WHERE app_id=?",
                (app_id,),
            ).fetchone()
            round_no = int(row[0]) + 1
        cur = conn.execute(
            "INSERT INTO interview_rounds "
            "(app_id, round_no, kind, scheduled_at, interviewer, notes, outcome) "
            "VALUES (?,?,?,?,?,?,?)",
            (app_id, round_no, kind, scheduled_at, interviewer, notes, outcome),
        )
        conn.commit()
        new_id = cur.lastrowid
        cur_status_row = conn.execute(
            "SELECT status FROM applications WHERE id=?", (app_id,)
        ).fetchone()
    # Advance a pre-interview status OUTSIDE the connection above so update_job's
    # own transaction (which records the status_history transition + follow-up
    # side-effects) doesn't nest connections on the same db.
    if cur_status_row and cur_status_row["status"] in _PRE_INTERVIEW_STATUSES:
        implied = _ROUND_KIND_STATUS.get(kind, "interview")
        update_job(app_id, status=implied)
    return new_id


def list_interview_rounds(app_id) -> list[dict]:
    """All interview rounds for an application, ordered by round_no then id."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM interview_rounds WHERE app_id=? ORDER BY round_no, id",
            (app_id,),
        ).fetchall()
    return [dict(r) for r in rows]


_ROUND_EDITABLE = {"round_no", "kind", "scheduled_at", "interviewer", "notes",
                   "outcome"}


def update_interview_round(round_id, **fields) -> None:
    # Same silent-data-loss guard as update_job (S32/L3): reject unknown round
    # field names rather than dropping them without a signal.
    _reject_unknown_fields("update_interview_round", fields, _ROUND_EDITABLE)
    updates = {k: v for k, v in fields.items() if k in _ROUND_EDITABLE}
    if not updates:
        return
    set_clause = ", ".join(f"{k}=?" for k in updates)
    with get_conn() as conn:
        conn.execute(
            f"UPDATE interview_rounds SET {set_clause} WHERE id=?",
            (*updates.values(), round_id),
        )
        conn.commit()


def delete_interview_round(round_id) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM interview_rounds WHERE id=?", (round_id,))
        conn.commit()


def get_interview_round(round_id) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM interview_rounds WHERE id=?", (round_id,)
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

def _url_host(url: str) -> str:
    """Lowercased netloc of a URL ('' when absent/unparseable). Used to keep
    job_key coalescing cross-source-only: same-host distinct URLs are distinct
    requisitions on one board, never duplicates."""
    try:
        from urllib.parse import urlparse
        return (urlparse(url or "").netloc or "").lower()
    except Exception:
        return ""


def _inbox_norm_url(job) -> str:
    """The stable inbox identity URL for a JobResult. A real posting keys on its
    normalized URL; a URL-LESS posting keys on a synthetic 'keyless:' + its
    canonical keyless identity (company|title|location bucket) so it (a) can't die
    silently at the inbox door for want of a UNIQUE norm_url and (b) dedupes
    against ITSELF across runs. The keyless identity is the SAME string the search
    engine dedups on (search.search_engine.keyless_identity), so engine dedup and
    inbox identity agree."""
    n = normalize_url(getattr(job, "url", "") or "")
    if n:
        return n
    from search.search_engine import keyless_identity
    return "keyless:" + keyless_identity(job)


def inbox_add_many(jobs, per_company_cap: int = 0, new_batch: str = "",
                   overflow_out: dict | None = None) -> int:
    """Insert JobResults into the inbox; silently skips postings already in the
    inbox, tracker, or dismissed list. Returns how many were actually added.

    per_company_cap > 0 enforces the cap against the PERSISTED inbox: a company
    already at N rows can only take (cap - N) more, so a board can't accrue
    cap rows per run and pile up over many runs. jobs is assumed best-first so
    the surviving rows are each company's top matches. 0 disables the cap.

    overflow_out (optional out-param, C1): when a dict is passed, it is populated
    IN PLACE with {company_display: n_capped} for companies whose cap was hit this
    run - so daily_run can log 'capped: Acme 12, SpaceX 9' and store it in the run
    record. Kept as an out-param (not a changed return type) so every existing
    caller that ignores overflow keeps its int return unchanged.

    Cross-source coalescing (C1): after the norm_url anti-join, a candidate whose
    job_key matches an existing inbox row's (non-NULL) job_key is treated as the
    SAME posting surfaced via a different URL (an overlap source). Instead of a
    second row it MERGES into the existing one - keeps the earlier date_added,
    fills in a description the old row lacked, and records the alternate URL under
    extras['alt_urls']. This is what stops the inbox double-listing once overlap
    sources (serpapi probe, CareerOneStop vs ATS) go live. NULL job_keys (old rows,
    or a build without the coverage bundle) never coalesce - treated as no-key.

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
    # URL-less jobs get a synthetic 'keyless:' norm_url and are NOT part of the
    # tracked/dismissed URL anti-join (those tables key on real URLs); their
    # dedup is the inbox's own UNIQUE norm_url (self-dedup across runs) plus the
    # job_key coalescing below.
    norm_by_job = [(j, _inbox_norm_url(j)) for j in jobs]
    real_urls = [n for j, n in norm_by_job
                 if n and not n.startswith("keyless:") and normalize_url(getattr(j, "url", "") or "")]
    unseen = urls_not_seen(real_urls)
    today = date.today().isoformat()
    # Start the running tally from what's already persisted so the cap spans runs.
    per_company = inbox_company_counts() if per_company_cap > 0 else {}
    cap_display = inbox_company_display_names() if per_company_cap > 0 else {}
    overflow: dict[str, int] = {}
    # Same-run job_key coalescing: two overlap sources in ONE batch surfacing the
    # same posting must also collapse, not just cross-run. Maps job_key -> the
    # inbox id we inserted (or merged into) this run.
    run_keys: dict[str, tuple] = {}  # job_key -> (inbox id, url host)
    added = 0
    with get_conn() as conn:
        for j, norm in norm_by_job:
            if not norm:
                continue
            is_keyless = norm.startswith("keyless:")
            # Real-URL jobs must clear the tracked/dismissed anti-join; keyless
            # jobs skip it (nothing tracks them by URL) and rely on norm_url +
            # job_key dedup.
            if not is_keyless and norm not in unseen:
                continue
            jk = getattr(j, "job_key", None) or None
            # -- job_key coalescing (C1) -------------------------------------
            # A non-NULL job_key match via a DIFFERENT host means the same
            # posting reached us through two routes (aggregator vs ATS): merge
            # into the existing row and skip the insert. NULL keys never
            # coalesce. CROSS-SOURCE ONLY: two DISTINCT URLs on the SAME host
            # are distinct requisitions (hospitals post many identically-titled
            # reqs on one board) and must NOT merge — coalescing them silently
            # drops real openings (review-fleet critical finding).
            if jk:
                cand_host = _url_host(getattr(j, "url", "") or "")
                hit = run_keys.get(jk)
                if hit is None:
                    ex = conn.execute(
                        "SELECT id, url FROM inbox WHERE job_key=? LIMIT 1", (jk,)
                    ).fetchone()
                    if ex is not None:
                        hit = (ex["id"], _url_host(ex["url"] or ""))
                if hit is not None:
                    target_id, ex_host = hit
                    same_board = bool(cand_host) and cand_host == ex_host
                    if not same_board:
                        _inbox_coalesce(conn, target_id, j, norm)
                        run_keys[jk] = hit
                        continue
                    # Same-host distinct req: keep it as its own row. Later
                    # same-run candidates with this key still compare against
                    # the FIRST row (good enough — an ambiguous cross-source
                    # dup of one-of-N identical reqs is unresolvable by key).
                    run_keys.setdefault(jk, hit)
            if per_company_cap > 0:
                key = (j.company or "").lower().strip()
                if per_company.get(key, 0) >= per_company_cap:
                    if key:
                        disp = cap_display.get(key, j.company or key)
                        overflow[disp] = overflow.get(disp, 0) + 1
                    continue
            cur = conn.execute(
                """INSERT OR IGNORE INTO inbox
                   (norm_url, title, company, location, url, salary_text,
                    description, source, score, score_notes, created, date_added,
                    board_count, job_key)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (norm, j.title, j.company, j.location, j.url,
                 j.salary_display(), (j.description or "")[:5000],
                 j.source_api, j.score, j.score_notes, j.created, today,
                 getattr(j, "board_count", -1), jk),
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
                if jk:
                    # (id, host) tuple — same shape as the coalesce branch reads.
                    run_keys.setdefault(jk, (cur.lastrowid, cand_host))
                if per_company_cap > 0:
                    per_company[key] = per_company.get(key, 0) + 1
            added += cur.rowcount
        if added:
            _fts_optimize(conn)
        conn.commit()
    if overflow_out is not None:
        overflow_out.update(overflow)
    return added


def _inbox_coalesce(conn, target_id: int, job, alt_norm: str) -> None:
    """Merge an overlap-source duplicate into the existing inbox row `target_id`
    (same posting, different URL): keep the earlier date_added (leave it as-is),
    fill in a description the old row lacked, and append the alternate URL under
    extras['alt_urls'] (de-duplicated). Never touches the score/fit (the existing
    triaged row wins). Best-effort on a missing row - no-op."""
    import json
    row = conn.execute(
        "SELECT description, extras FROM inbox WHERE id=?", (target_id,)
    ).fetchone()
    if row is None:
        return
    # Prefer whichever row HAS a description: fill the old row's blank from the new.
    new_desc = (getattr(job, "description", "") or "").strip()
    if new_desc and not (row["description"] or "").strip():
        conn.execute("UPDATE inbox SET description=? WHERE id=?",
                     (new_desc[:5000], target_id))
    # Record the alternate URL (the merged posting's own URL, else its keyless id)
    # under extras['alt_urls'] so the coalesced posting's other surface isn't lost.
    alt = normalize_url(getattr(job, "url", "") or "") or alt_norm
    current = {}
    if row["extras"]:
        try:
            loaded = json.loads(row["extras"])
            if isinstance(loaded, dict):
                current = loaded
        except (ValueError, TypeError):
            current = {}
    alts = current.get("alt_urls")
    if not isinstance(alts, list):
        alts = []
    if alt and alt not in alts:
        alts.append(alt)
        current["alt_urls"] = alts
        conn.execute("UPDATE inbox SET extras=? WHERE id=?",
                     (json.dumps(current, separators=(",", ":")), target_id))


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


def export_applications_csv(path) -> int:
    """Dump every application (with its status_history joined in) to a CSV at
    `path` using the csv stdlib. One row per application; the whole status
    timeline is folded into a 'history' column as 'changed_at old->new [note]'
    entries separated by ' | ', so a single spreadsheet carries the full cycle.
    Returns the number of application rows written."""
    import csv
    fields = [
        "id", "title", "company", "location", "status", "url", "salary_text",
        "source", "date_added", "date_applied", "follow_up_date", "deadline",
        "contact", "offer_amount", "offer_deadline", "offer_notes", "notes",
        "history",
    ]
    with get_conn() as conn:
        apps = [dict(r) for r in conn.execute(
            "SELECT * FROM applications WHERE archived=0 ORDER BY id"
        ).fetchall()]
        hist: dict[int, list[str]] = {}
        for ev in status_timeline_all(conn):
            note = f" [{ev['note']}]" if ev["note"] else ""
            # A same-status row carrying a note is an add_status_note() event, not
            # a real transition (S32/L6). The interactive timeline already tags it
            # kind='note'; render it as a note here too instead of emitting a
            # phantom 'accepted->accepted' self-transition in the exported CSV.
            if ev["old_status"] == ev["new_status"] and ev["note"]:
                entry = f"{ev['changed_at']} {ev['new_status']} [note: {ev['note']}]"
            else:
                entry = f"{ev['changed_at']} {ev['old_status']}->{ev['new_status']}{note}"
            hist.setdefault(ev["job_id"], []).append(entry)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for a in apps:
            a["history"] = " | ".join(hist.get(a["id"], []))
            w.writerow(a)
    return len(apps)


def status_timeline_all(conn) -> list[dict]:
    """Every status_history event across all jobs (for CSV export), oldest first
    per job. Tolerant of a pre-v7 db with no `note` column."""
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(status_history)")}
    has_note = "note" in cols
    sel = "job_id, old_status, new_status, changed_at" + (", note" if has_note else "")
    out = []
    for r in conn.execute(
        f"SELECT {sel} FROM status_history ORDER BY job_id, changed_at, id"
    ).fetchall():
        out.append({
            "job_id": r["job_id"], "old_status": r["old_status"],
            "new_status": r["new_status"], "changed_at": r["changed_at"],
            "note": (r["note"] if has_note else "") or "",
        })
    return out


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
