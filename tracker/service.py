"""Intent-verb service layer for the job tracker, mirroring resume/service.py:
the desktop GUI calls these verbs instead of reaching into ~18 tracker.db
symbols directly, and the view-side dedup + fit-prompt-from-rows logic lives
here rather than in the tkinter view.

Mutating verbs (track_job, dismiss_job, archive_job, ...) wrap the underlying
db calls; read/transform helpers (dedup_new_jobs, fit_prompt_for_rows,
apply_fit_scores) keep the dedup and Claude-bridge plumbing out of gui.py.
"""
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tracker import db


# ── Tracker mutations (applications table) ────────────────────────────────────

def add_manual_job(**fields) -> int:
    """Insert a manually-entered application; returns the new id."""
    return db.add_job(**fields)


def update_job(job_id: int, **fields) -> None:
    db.update_job(job_id, **fields)


def archive_job(job_id: int) -> None:
    db.archive_job(job_id)


def restore_job(job_id: int) -> None:
    db.unarchive_job(job_id)


def delete_job(job_id: int) -> None:
    db.delete_job(job_id)


def get_job(job_id: int) -> dict | None:
    return db.get_job(job_id)


def list_jobs(status_filter=None) -> list[dict]:
    return db.get_all(status_filter)


def counts() -> dict:
    return db.get_counts()


def set_status(job_id: int, status: str) -> None:
    db.update_job(job_id, status=status)


# ── Inbox triage ──────────────────────────────────────────────────────────────

def list_inbox() -> list[dict]:
    return list(db.inbox_all())


def inbox_size() -> int:
    return db.inbox_count()


def track_job(inbox_id: int) -> int | None:
    """Promote an inbox row to a tracked application; returns the new app id."""
    return db.inbox_track(inbox_id)


def dismiss_job(inbox_id: int) -> None:
    """Dismiss an inbox row (hidden from all future searches/daily runs)."""
    db.inbox_dismiss(inbox_id)


# Inbox columns we can round-trip for Undo (id/rk are not re-inserted; id is
# reassigned, rk is a query artifact).
_INBOX_RESTORE_COLS = (
    "norm_url", "title", "company", "location", "url", "salary_text",
    "description", "source", "score", "score_notes", "fit", "fit_why",
    "created", "date_added", "board_count",
)


def restore_dismissed_rows(rows: list[dict]) -> int:
    """Undo a dismiss: re-insert previously-dismissed inbox row dicts and drop
    their URLs from the dismissed set so they're visible again. Returns how many
    rows were restored. Rows already present (norm_url UNIQUE) are skipped."""
    from datetime import date
    if not rows:
        return 0
    today = date.today().isoformat()
    restored = 0
    with db.get_conn() as conn:
        for r in rows:
            norm = r.get("norm_url") or db.normalize_url(r.get("url", ""))
            if not norm:
                continue
            vals = []
            for col in _INBOX_RESTORE_COLS:
                if col == "norm_url":
                    vals.append(norm)
                elif col == "date_added":
                    vals.append(r.get("date_added") or today)
                else:
                    vals.append(r.get(col, ""))
            placeholders = ",".join("?" for _ in _INBOX_RESTORE_COLS)
            cur = conn.execute(
                f"INSERT OR IGNORE INTO inbox ({','.join(_INBOX_RESTORE_COLS)}) "
                f"VALUES ({placeholders})", vals)
            if cur.rowcount:
                conn.execute("DELETE FROM dismissed WHERE url=?", (norm,))
                restored += 1
        conn.commit()
    return restored


def set_inbox_fit(inbox_id: int, fit: int, why: str) -> None:
    db.inbox_set_fit(inbox_id, fit, why)


# ── Search-side dedup + track ─────────────────────────────────────────────────

def seen_urls() -> set[str]:
    return db.seen_urls()


def normalize_url(url: str) -> str:
    return db.normalize_url(url)


def dismiss_url(url: str) -> None:
    db.dismiss_url(url)


def dedup_new_jobs(jobs, seen: set[str] | None = None):
    """Split search results into (new, skipped_count) against the tracked +
    dismissed URL set. Moves the view-side dedup loop out of the GUI."""
    if seen is None:
        seen = db.seen_urls()
    new = []
    skipped = 0
    for j in jobs:
        if db.normalize_url(j.url) in seen:
            skipped += 1
            continue
        new.append(j)
    return new, skipped


def track_search_results(jobs, seen: set[str] | None = None) -> tuple[int, int]:
    """Add search results as 'interested' applications, skipping any already
    tracked/dismissed. Returns (added, skipped)."""
    if seen is None:
        seen = db.seen_urls()
    new, skipped = dedup_new_jobs(jobs, seen)
    for j in new:
        db.add_job(
            title=j.title, company=j.company, location=j.location,
            url=j.url, salary_text=j.salary_display(),
            source=j.source_api, status="interested",
            description=(j.description or "")[:5000], score=j.score,
        )
    return len(new), skipped


# ── Fit-scoring bridge (rows -> prompt; reply -> scores) ──────────────────────

def jobs_from_rows(rows: list[dict]) -> list:
    """Rebuild a JobResult per inbox/queue row, carrying the row's DB id in
    JobResult.job_id so token-verified scores can be written back to the right
    row. Prepends the stored salary text so a rebuilt result doesn't report
    'Not listed' for a salary we already know."""
    from models import JobResult
    return [JobResult(
        title=r["title"], company=r["company"], location=r.get("location", ""),
        salary_min=None, salary_max=None,
        description=f"Salary: {r.get('salary_text', '')}\n{r.get('description', '')}",
        url=r.get("url", ""), source_keyword="", created=r.get("created", ""),
        job_id=str(r["id"]), board_count=r.get("board_count", -1),
    ) for r in rows]


def fit_prompt_for_rows(rows: list[dict]) -> tuple[str, list]:
    """Build a Claude fit-scoring prompt from inbox/queue row dicts. Returns
    (prompt, jobs) where jobs is the JobResult list (each carrying its row id in
    .job_id). Pass the same jobs list to score_*_from_reply so scores map back
    by the prompt's echoed token, not by reply position."""
    import ranker
    jobs = jobs_from_rows(rows)
    # Rank against the user's preferences.md profile (what they want) plus their
    # experience summary (what they can do) — the shared ranker request, so the
    # bridge, API, and MCP routes all score identically.
    prompt = ranker.build_request(jobs)
    return prompt, jobs


def unscored_inbox_rows(rows, per_company: int = 2, limit: int = 20) -> list[dict]:
    """Pick a diverse batch of still-unscored rows: at most `per_company` per
    company so one mega-board can't burn all the slots. Input order is assumed
    round-robin (inbox_all), so repeated rounds walk down the inbox."""
    from collections import defaultdict
    seen: dict[str, int] = defaultdict(int)
    out: list[dict] = []
    for r in rows:
        if (r.get("fit", -1) or -1) >= 0:
            continue
        key = (r.get("company") or "").lower()
        if seen[key] >= per_company:
            continue
        seen[key] += 1
        out.append(r)
        if len(out) >= limit:
            break
    return out


def parse_fit_reply(reply: str, expected: int) -> list[dict]:
    """Parse a pasted Claude fit reply into a list of score dicts (preserving
    reply order). Raises claude_bridge.BridgeParseError on unparseable input."""
    from claude_bridge import parse_fit_response
    return parse_fit_response(reply, expected)


def match_fit(jobs, parsed) -> list:
    """Token-verified mapping of parsed fit results onto jobs via the
    claude_bridge helper. Returns a list of (job, fit_score, rationale) tuples
    in jobs order. Falls back to positional matching if the helper is absent."""
    import claude_bridge
    helper = getattr(claude_bridge, "match_fit_to_jobs", None)
    if helper is not None:
        return helper(jobs, parsed)
    # Fallback: trust positional order (parsed[k] -> jobs[k]).
    out = []
    for k, item in enumerate(parsed):
        if k < len(jobs) and isinstance(item, dict):
            out.append((jobs[k], item.get("fit_score", 0),
                        item.get("rationale", "")))
    return out


def score_inbox_from_reply(jobs, reply: str) -> int:
    """Parse a fit reply and write token-verified scores back to inbox rows
    (jobs carry their row id in .job_id). Returns how many were applied."""
    parsed = parse_fit_reply(reply, len(jobs))
    applied = 0
    for job, fit_score, rationale in match_fit(jobs, parsed):
        if not job.job_id:
            continue
        db.inbox_set_fit(int(job.job_id), fit_score, rationale)
        applied += 1
    return applied


def score_applications_from_reply(jobs, reply: str) -> int:
    """Parse a fit reply and write token-verified scores back to tracked
    applications (jobs carry the app id in .job_id). Returns how many applied."""
    parsed = parse_fit_reply(reply, len(jobs))
    applied = 0
    for job, fit_score, rationale in match_fit(jobs, parsed):
        if not job.job_id:
            continue
        db.update_job(int(job.job_id), fit_score=fit_score,
                      fit_rationale=rationale)
        applied += 1
    return applied


# ── Re-rank round-trip (WS-3) ─────────────────────────────────────────────────

def inbox_rows_by_key() -> dict:
    """{job_key -> inbox-row dict} for the file round-trip join. The key is the
    WS-1 cross-source identity when present, else JobResult.identity_key (the
    _job_key_for_row helper does `getattr(j, "job_key", None) or j.identity_key`,
    so this works before OR after WS-1 lands). On a key collision the first row
    wins (round-robin order is stable)."""
    from rerank.schema import _job_key_for_row
    out: dict = {}
    for r in db.inbox_all():
        key = _job_key_for_row(r)
        out.setdefault(key, r)
    return out


def apply_rerank_scores(updates: list[dict], *, source: str = "file_import") -> int:
    """Write imported re-rank scores back to the inbox: new_fit -> fit,
    fit_rationale -> fit_why (via inbox_set_fit, which snapshots score_history),
    and the optional extras JSON blob -> inbox.extras. Returns rows updated."""
    applied = 0
    for u in updates:
        try:
            inbox_id = int(u["id"])
            fit = max(0, min(100, int(u["new_fit"])))
        except (KeyError, TypeError, ValueError):
            continue
        db.inbox_set_fit(inbox_id, fit, str(u.get("fit_rationale", "") or ""),
                         source=source)
        extras = u.get("extras")
        if extras:
            db.inbox_set_extras(inbox_id, str(extras))
        applied += 1
    return applied


def undo_last_rerank(scope: str = "file_import") -> int:
    """Revert the most recent re-rank batch (by source scope). Returns rows
    restored. scope='any' ignores the source tag."""
    return db.inbox_undo_last_rerank(scope)


# ── Top Picks (AI shortlist over the whole inbox) ─────────────────────────────

def new_rec_batch() -> str:
    """A fresh recommendation-batch stamp (UTC ISO, second precision). One per
    set_fit_scores / import call, so a newer AI run's picks supersede the old."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def rank_patch(rank: int, batch: str, tags: str | None = None) -> dict:
    """The extras keys a shortlist write stamps onto an inbox row. ONE place
    defines the shape so the MCP and file-import paths agree."""
    patch = {"rank": int(rank), "rec_batch": batch}
    if tags is not None and str(tags).strip():
        patch["tags"] = str(tags)
    return patch


def _parse_extras(raw) -> dict:
    if not raw:
        return {}
    try:
        d = json.loads(raw)
        return d if isinstance(d, dict) else {}
    except (ValueError, TypeError):
        return {}


def read_rank(row: dict) -> int:
    """The AI shortlist rank on an inbox row (1=best), or -1 if unranked/bad."""
    try:
        return int(_parse_extras(row.get("extras")).get("rank"))
    except (TypeError, ValueError):
        return -1


def _rec_batch_of(row: dict) -> str:
    return str(_parse_extras(row.get("extras")).get("rec_batch", "") or "")


def top_picks(limit: int = 10) -> list[dict]:
    """The current AI recommendation: inbox rows in the latest rec_batch,
    ordered by rank ascending, capped at `limit` (0 = every ranked row). Each
    returned dict is an inbox row augmented with an int 'rank' key for display.
    Returns [] when nothing has been ranked yet."""
    ranked = [(read_rank(r), r) for r in db.inbox_all()]
    ranked = [(rk, r) for rk, r in ranked if rk >= 1]
    if not ranked:
        return []
    latest = max(_rec_batch_of(r) for _, r in ranked)
    picks = [dict(r, rank=rk) for rk, r in ranked if _rec_batch_of(r) == latest]
    picks.sort(key=lambda r: r["rank"])
    if limit and limit > 0:
        picks = picks[:limit]
    return picks
