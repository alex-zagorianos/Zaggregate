import sqlite3
import sys
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import BASE_DIR

DB_PATH = BASE_DIR / "tracker.db"

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
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _existing_columns(conn) -> set[str]:
    return {r["name"] for r in conn.execute("PRAGMA table_info(applications)")}


def init_db():
    with get_conn() as conn:
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
        conn.commit()


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
    updates = {k: v for k, v in fields.items() if k in _EDITABLE}
    if not updates:
        return
    set_clause = ", ".join(f"{k}=?" for k in updates)
    with get_conn() as conn:
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

def normalize_url(url: str) -> str:
    """Canonicalize a URL for dedup: drop scheme, query, fragment, trailing
    slash, and lowercase the host so the same posting matches across runs."""
    if not url:
        return ""
    parts = urlsplit(url.strip())
    host = (parts.netloc or "").lower()
    path = (parts.path or "").rstrip("/")
    return f"{host}{path}" if host else path


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

def inbox_add_many(jobs) -> int:
    """Insert JobResults into the inbox; silently skips postings already in the
    inbox, tracker, or dismissed list. Returns how many were actually added."""
    from datetime import date
    seen = seen_urls()
    today = date.today().isoformat()
    added = 0
    with get_conn() as conn:
        for j in jobs:
            norm = normalize_url(j.url)
            if not norm or norm in seen:
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
    if order == "roundrobin":
        sql = (
            f"SELECT *, ROW_NUMBER() OVER "
            f"(PARTITION BY company ORDER BY {rank} DESC, date_added DESC) AS rk "
            f"FROM inbox ORDER BY rk, {rank} DESC, date_added DESC"
        )
    else:
        sql = f"SELECT * FROM inbox ORDER BY {rank} DESC, date_added DESC"
    with get_conn() as conn:
        rows = conn.execute(sql).fetchall()
    out = [dict(r) for r in rows]
    for r in out:
        r.pop("rk", None)
    return out


def inbox_set_fit(inbox_id: int, fit: int, why: str):
    with get_conn() as conn:
        conn.execute("UPDATE inbox SET fit=?, fit_why=? WHERE id=?",
                     (fit, why, inbox_id))
        conn.commit()


def inbox_count() -> int:
    with get_conn() as conn:
        return conn.execute("SELECT COUNT(*) FROM inbox").fetchone()[0]


def inbox_delete(inbox_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM inbox WHERE id=?", (inbox_id,))
        conn.commit()


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
