import sqlite3
import sys
from pathlib import Path

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


def get_conn():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


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
        conn.commit()


def add_job(title, company, location="", url="", salary_text="",
            source="manual", status="interested", date_added="",
            date_applied="", notes=""):
    from datetime import date
    if not date_added:
        date_added = date.today().isoformat()
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO applications
               (title, company, location, url, salary_text, source,
                status, date_added, date_applied, notes)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (title, company, location, url, salary_text, source,
             status, date_added, date_applied, notes),
        )
        conn.commit()
        return cur.lastrowid


def get_all(status_filter=None):
    with get_conn() as conn:
        if status_filter and status_filter != "all":
            rows = conn.execute(
                "SELECT * FROM applications WHERE status=? ORDER BY date_added DESC",
                (status_filter,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM applications ORDER BY date_added DESC"
            ).fetchall()
    return [dict(r) for r in rows]


def get_counts():
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT status, COUNT(*) as n FROM applications GROUP BY status"
        ).fetchall()
    counts = {s: 0 for s in STATUSES}
    total = 0
    for r in rows:
        counts[r["status"]] = r["n"]
        total += r["n"]
    counts["all"] = total
    return counts


def update_job(job_id, **fields):
    allowed = {"status", "notes", "date_applied", "title", "company",
                "location", "url", "salary_text"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return
    set_clause = ", ".join(f"{k}=?" for k in updates)
    with get_conn() as conn:
        conn.execute(
            f"UPDATE applications SET {set_clause} WHERE id=?",
            (*updates.values(), job_id),
        )
        conn.commit()


def delete_job(job_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM applications WHERE id=?", (job_id,))
        conn.commit()


def get_job(job_id):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM applications WHERE id=?", (job_id,)
        ).fetchone()
    return dict(row) if row else None
