"""``keyword_pool`` store + CRUD — the shared spine of Search Discovery.

Every candidate keyword the user has ever been shown lives here: its tier
(core/adjacent/exploratory/negative), provenance (onet/related_soc/corpus/ai/
manual/level_variant/resume), activation status (suggested/active/inactive), and
last-known live yield. The table is created in ``tracker.db.init_db`` (schema v8);
these helpers assume the schema exists exactly as every other ``tracker.db``
accessor does (the app calls ``init_db`` at startup; tests use the standard
``monkeypatch.setattr(db, "DB_PATH", ...); db.init_db()`` fixture).

Design rules baked in here:
  * ``upsert_terms`` NEVER downgrades an existing row — re-proposing an already
    ``active`` term as a ``suggested`` core suggestion just refreshes ``last_seen``.
    So a suggestion engine can re-run every day without clobbering user choices.
  * ``prune_suggestions`` only ever deletes ``status='suggested'`` rows — an
    ``active`` (or user-deactivated ``inactive``) term is never pruned, regardless
    of age or yield.
  * Nothing here reads ``cfg['keywords']`` or mutates scoring. The pool MIRRORS
    the search config; ``search.discovery`` callers keep the two in sync.

Pure of the GUI; import-safe (no tkinter). Returns plain dicts so the web API and
tests consume rows without touching ``sqlite3.Row``.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from tracker import db

# Public vocabularies (also the DB CHECK-free contract — validated here, not in
# SQL, so a bad value is a clean Python error, not a sqlite IntegrityError).
VALID_TIERS = ("core", "adjacent", "exploratory", "negative")
VALID_STATUSES = ("suggested", "active", "inactive")

_COLUMNS = ("id", "term", "tier", "source", "status", "yield_count",
            "yield_source", "yield_date", "first_seen", "last_seen",
            "activated_at")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_dict(r) -> dict:
    return {k: r[k] for k in _COLUMNS}


def upsert_terms(terms) -> int:
    """Insert candidate terms; refresh ``last_seen`` on ones already present.

    ``terms`` is an iterable of dicts: ``{"term": str, "tier": str, "source": str,
    "status"?: str}`` (``status`` defaults to ``"suggested"``). Blank terms and
    unknown tier/status values are skipped defensively (never raises on ordinary
    bad input). Duplicate terms WITHIN the batch are de-duplicated (first wins).

    An existing row is only ``last_seen``-touched — its tier/source/status are
    left intact so an ``active`` term a user chose is never silently reverted to a
    ``suggested`` core suggestion by a re-run. Returns the count of NEWLY inserted
    rows (existing-row refreshes are not counted)."""
    # Normalize + de-dupe the incoming batch (exact trimmed term, first wins).
    cleaned: dict[str, dict] = {}
    for t in terms or []:
        term = str((t or {}).get("term") or "").strip()
        tier = str((t or {}).get("tier") or "").strip()
        source = str((t or {}).get("source") or "").strip()
        status = str((t or {}).get("status") or "suggested").strip()
        if not term or tier not in VALID_TIERS or status not in VALID_STATUSES:
            continue
        if not source:
            continue
        cleaned.setdefault(term, {"term": term, "tier": tier, "source": source,
                                  "status": status})
    if not cleaned:
        return 0

    now = _now()
    inserted = 0
    with db.get_conn() as conn:
        existing = {r["term"] for r in conn.execute(
            "SELECT term FROM keyword_pool WHERE term IN (%s)"
            % ",".join("?" * len(cleaned)), tuple(cleaned.keys())).fetchall()}
        for term, row in cleaned.items():
            if term in existing:
                conn.execute("UPDATE keyword_pool SET last_seen=? WHERE term=?",
                             (now, term))
                continue
            activated = now if row["status"] == "active" else None
            conn.execute(
                "INSERT INTO keyword_pool "
                "(term, tier, source, status, first_seen, last_seen, activated_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (term, row["tier"], row["source"], row["status"], now, now,
                 activated))
            inserted += 1
        conn.commit()
    return inserted


def get_pool(status: str | None = None, tier: str | None = None) -> list[dict]:
    """Return pool rows (newest-first), optionally filtered by status and/or tier.
    An unknown filter value simply matches nothing (never raises)."""
    where, params = [], []
    if status is not None:
        where.append("status=?")
        params.append(status)
    if tier is not None:
        where.append("tier=?")
        params.append(tier)
    sql = "SELECT * FROM keyword_pool"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY id DESC"
    with db.get_conn() as conn:
        rows = conn.execute(sql, tuple(params)).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_term(term: str) -> dict | None:
    term = (term or "").strip()
    if not term:
        return None
    with db.get_conn() as conn:
        r = conn.execute("SELECT * FROM keyword_pool WHERE term=?", (term,)).fetchone()
    return _row_to_dict(r) if r is not None else None


def active_terms() -> list[str]:
    """The terms currently marked ``active`` — the pool's view of what should be
    searched. Callers keep ``cfg['keywords']`` in sync with this."""
    with db.get_conn() as conn:
        rows = conn.execute(
            "SELECT term FROM keyword_pool WHERE status='active' ORDER BY id").fetchall()
    return [r["term"] for r in rows]


def set_status(term: str, status: str) -> bool:
    """Move a term to a new status. Stamps ``activated_at`` the first time a term
    becomes ``active`` (and never clears it afterward, so the min-age flag guard
    in ``flag`` has a stable activation timestamp). Returns True if a row changed.
    Unknown status or missing term -> False (never raises)."""
    term = (term or "").strip()
    if not term or status not in VALID_STATUSES:
        return False
    with db.get_conn() as conn:
        row = conn.execute("SELECT activated_at FROM keyword_pool WHERE term=?",
                           (term,)).fetchone()
        if row is None:
            return False
        if status == "active" and not row["activated_at"]:
            conn.execute("UPDATE keyword_pool SET status=?, activated_at=? WHERE term=?",
                         (status, _now(), term))
        else:
            conn.execute("UPDATE keyword_pool SET status=? WHERE term=?", (status, term))
        conn.commit()
    return True


def set_yield(term: str, count: int | None, source: str = "") -> bool:
    """Record a live-probed opening count for a term (stamps ``yield_date`` = now).
    ``count`` may be None to record "probed, unknown". Returns True if a row
    changed. Missing term -> False."""
    term = (term or "").strip()
    if not term:
        return False
    with db.get_conn() as conn:
        cur = conn.execute(
            "UPDATE keyword_pool SET yield_count=?, yield_source=?, yield_date=? "
            "WHERE term=?",
            (count, source or "", _now(), term))
        conn.commit()
        return cur.rowcount > 0


def prune_suggestions(ttl_days: int = 90, now: str | None = None) -> int:
    """Delete stale SUGGESTED-only rows: ``status='suggested'`` and not seen in
    ``ttl_days``. NEVER touches ``active`` or ``inactive`` rows (a user-chosen or
    user-declined term is kept regardless of age). Returns the delete count.

    ``now`` (ISO string) is injectable so the age math is testable without
    clock-mocking."""
    cutoff = ((datetime.fromisoformat(now) if now else datetime.now(timezone.utc))
              - timedelta(days=ttl_days)).isoformat()
    with db.get_conn() as conn:
        cur = conn.execute(
            "DELETE FROM keyword_pool WHERE status='suggested' AND last_seen < ?",
            (cutoff,))
        conn.commit()
        return cur.rowcount
