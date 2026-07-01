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


# ── Application cycle: notes, timeline, interview rounds, contacts (D1) ────────

def add_status_note(job_id: int, note: str) -> int | None:
    """Attach a timestamped note to an application without changing its status."""
    return db.add_status_note(job_id, note)


def status_timeline(job_id: int) -> list[dict]:
    """Read-only chronological timeline (status changes + notes) for a job."""
    return db.status_timeline(job_id)


def add_interview_round(app_id: int, **fields) -> int:
    return db.add_interview_round(app_id, **fields)


def list_interview_rounds(app_id: int) -> list[dict]:
    return db.list_interview_rounds(app_id)


def update_interview_round(round_id: int, **fields) -> None:
    db.update_interview_round(round_id, **fields)


def delete_interview_round(round_id: int) -> None:
    db.delete_interview_round(round_id)


def get_interview_round(round_id: int) -> dict | None:
    return db.get_interview_round(round_id)


def contacts_for_company(company: str) -> list[dict]:
    """People the user knows at a company — for the 'consider a referral' nudge
    surfaced in the Apply Queue detail pane and the Tracker edit dialog."""
    return db.contacts_for_company(company)


def referral_hint(company: str) -> str:
    """One-line referral nudge for a company, or '' when no contacts are known.
    'You know 2 people at Acme: Jane Doe, John Roe - consider asking for a
    referral.' (referrals are the highest-conversion channel)."""
    people = db.contacts_for_company(company)
    if not people:
        return ""
    names = ", ".join(p["name"] for p in people if p.get("name"))
    n = len(people)
    who = "person" if n == 1 else "people"
    tail = f": {names}" if names else ""
    return (f"You know {n} {who} at {company}{tail} - "
            "consider asking for a referral.")


def add_contact(name: str, **fields) -> int:
    """Record a networking contact (optionally linked to an app_id +
    last_contacted). Thin pass-through so the GUI Contacts dialog goes through
    the service layer like every other mutation."""
    return db.add_contact(name, **fields)


# ── ICS calendar export for interview rounds (stdlib-only) ────────────────────

def round_to_ics(app: dict, rnd: dict) -> str:
    """Build a minimal RFC-5545 VEVENT for a scheduled interview round (stdlib
    only, no deps). `rnd['scheduled_at']` is an ISO datetime; a bare date is
    treated as an all-day-ish 1-hour block at 09:00 local. Returns the full
    VCALENDAR text. Raises ValueError when the round has no scheduled_at."""
    from datetime import datetime, timedelta
    sched = (rnd.get("scheduled_at") or "").strip()
    if not sched:
        raise ValueError("This interview round has no scheduled date/time.")
    try:
        start = datetime.fromisoformat(sched)
    except ValueError:
        start = datetime.strptime(sched[:10], "%Y-%m-%d").replace(hour=9)
    end = start + timedelta(hours=1)

    def _fmt(dt) -> str:
        # Floating local time (no Z): calendar apps read it in the user's zone.
        return dt.strftime("%Y%m%dT%H%M%S")

    def _esc(s) -> str:
        # RFC-5545 TEXT escaping: backslash, semicolon, comma, newline.
        return (str(s or "").replace("\\", "\\\\").replace(";", "\\;")
                .replace(",", "\\,").replace("\r\n", "\\n")
                .replace("\n", "\\n"))

    company = app.get("company", "") or ""
    title = app.get("title", "") or ""
    kind = (rnd.get("kind") or "other").title()
    summary = f"{kind} interview - {company}".strip(" -")
    desc_bits = []
    if title:
        desc_bits.append(f"Role: {title}")
    if rnd.get("interviewer"):
        desc_bits.append(f"Interviewer: {rnd['interviewer']}")
    if rnd.get("notes"):
        desc_bits.append(str(rnd["notes"]))
    if app.get("url"):
        desc_bits.append(f"Posting: {app['url']}")
    description = "  ".join(desc_bits)
    from datetime import timezone
    uid = f"jobscout-round-{rnd.get('id', 0)}-{app.get('id', 0)}@jobscout.local"
    dtstamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//JobScout//Interview Rounds//EN",
        "CALSCALE:GREGORIAN",
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{dtstamp}",
        f"DTSTART:{_fmt(start)}",
        f"DTEND:{_fmt(end)}",
        f"SUMMARY:{_esc(summary)}",
    ]
    if description:
        lines.append(f"DESCRIPTION:{_esc(description)}")
    if company:
        lines.append(f"LOCATION:{_esc(company)}")
    lines += ["END:VEVENT", "END:VCALENDAR"]
    return "\r\n".join(lines) + "\r\n"


def write_round_ics(app: dict, rnd: dict, out_dir) -> "Path":
    """Write the VEVENT for a round to <out_dir>/interview-<company>-r<n>.ics and
    return the file path. Caller opens the containing folder."""
    from pathlib import Path as _Path
    import re as _re
    out = _Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    slug = _re.sub(r"[^A-Za-z0-9]+", "-", (app.get("company") or "job")).strip("-") or "job"
    name = f"interview-{slug}-r{rnd.get('round_no', 0)}.ics"
    path = out / name
    path.write_text(round_to_ics(app, rnd), encoding="utf-8")
    return path


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
    "created", "date_added", "board_count", "extras",
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


# A nominal low fit recorded for jobs the deterministic gate auto-filters, so they
# stop re-surfacing in the next "rank these" round and the user can see WHY (the
# "Auto-filtered:" rationale). Distinct from a real AI judgment.
_GATE_FIT = 10


def compact_fit_prompt_for_rows(rows: list[dict], prefs: dict | None = None,
                                cfg: dict | None = None) -> tuple[str, list, list]:
    """Compact, gated fit prompt (spec-2026-06-29): each job is fed as extracted
    FACTS + a rubric instead of its raw description (~60% less context), and
    structural non-fits (internship / clearance / foreign-visa / people-management
    / excluded title / over-senior) are gated out before the prompt — no AI spend.

    Returns (prompt, kept_jobs, dropped):
      - kept_jobs: JobResults carrying each row's id in .job_id; pass to
        score_*_from_reply (token-matched write-back, unchanged).
      - dropped: [{"id", "title", "company", "reasons":[...]}] excluded from the AI
        batch. They keep their local score; pass to mark_inbox_gated so they don't
        re-surface.
    """
    import ranker
    jobs = jobs_from_rows(rows)
    res = ranker.prepare_compact(jobs, prefs=prefs, cfg=cfg)
    kept_jobs = [j for j, _f, _g in res["kept"]]
    dropped = [{"id": int(j.job_id) if getattr(j, "job_id", None) else None,
                "title": j.title, "company": j.company, "reasons": g["reasons"]}
               for j, _f, g in res["dropped"]]
    return res["prompt"], kept_jobs, dropped


def mark_inbox_gated(dropped: list[dict]) -> int:
    """Record auto-gated inbox jobs with a low fit + an "Auto-filtered:" reason so
    they don't re-surface in the next rank round and the user sees why. Returns how
    many rows were marked (those carrying a row id)."""
    n = 0
    for d in dropped:
        if d.get("id") is None:
            continue
        why = "Auto-filtered: " + ", ".join(d.get("reasons", []))
        db.inbox_set_fit(int(d["id"]), _GATE_FIT, why, source="gate")
        n += 1
    return n


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


def score_inbox_from_reply(jobs, reply: str, *, source: str = "bridge"):
    """Parse a fit reply, write token-verified fits back to inbox rows under ONE
    shared batch (so Undo can revert the whole set atomically regardless of
    route), AND derive a Top-Picks shortlist (rank best-first) so the free
    clipboard round-trip fills the Top Picks tab without the file-import/MCP path.

    `source` tags the batch ('bridge' for the clipboard paste, 'api' for the auto
    route) so undo scope='any' still reverts across routes.

    Returns (applied, missed):
      applied — jobs whose score actually landed on an inbox row.
      missed  — [{"title","company"}] for jobs we ASKED to score but that got no
                score back (dropped/skipped by the model, or a write that didn't
                land) — surfaced by the GUI as 'Scored X/N - k not scored', at
                parity with the file-import unmatched reporting.
    """
    parsed = parse_fit_reply(reply, len(jobs))
    batch = new_rec_batch()
    scored = []  # (inbox_id, fit)
    scored_ids = set()
    for job, fit_score, rationale in match_fit(jobs, parsed):
        if not job.job_id:
            continue
        if db.inbox_set_fit(int(job.job_id), fit_score, rationale,
                            source=source, batch=batch):
            scored.append((int(job.job_id), fit_score))
            scored_ids.add(str(job.job_id))
    if scored:
        for rank, (jid, _fit) in enumerate(
                sorted(scored, key=lambda t: -t[1]), start=1):
            db.inbox_merge_extras(jid, rank_patch(rank, batch))
    missed = [{"title": getattr(j, "title", ""), "company": getattr(j, "company", "")}
              for j in jobs
              if getattr(j, "job_id", None) and str(j.job_id) not in scored_ids]
    return len(scored), missed


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
    and the optional extras blob MERGED into inbox.extras (preserving
    new_batch/browse/etc). Returns rows updated."""
    import uuid
    batch = uuid.uuid4().hex[:12]
    applied = 0
    for u in updates:
        try:
            inbox_id = int(u["id"])
            fit = max(0, min(100, int(u["new_fit"])))
        except (KeyError, TypeError, ValueError):
            continue
        db.inbox_set_fit(inbox_id, fit, str(u.get("fit_rationale", "") or ""),
                         source=source, batch=batch)
        extras = u.get("extras")
        if extras:
            patch = extras if isinstance(extras, dict) else None
            if patch is None:
                try:
                    loaded = json.loads(extras)
                    patch = loaded if isinstance(loaded, dict) else None
                except (ValueError, TypeError):
                    patch = None
            if patch:
                db.inbox_merge_extras(inbox_id, patch)
        applied += 1
    return applied


def undo_last_rerank(scope: str = "file_import") -> int:
    """Revert the most recent re-rank batch (by source scope). Returns rows
    restored. scope='any' ignores the source tag."""
    return db.inbox_undo_last_rerank(scope)


# ── Top Picks (AI shortlist over the whole inbox) ─────────────────────────────

def new_rec_batch() -> str:
    """A fresh recommendation-batch stamp: UTC ISO (microsecond precision) + a
    short random suffix. One per set_fit_scores / import / reply call.

    Two properties matter:
      * time-ordered PREFIX so top_picks() can pick the newest batch by max()
        (a later run's picks supersede the old).
      * a UNIQUE suffix so two routes firing in the same instant get DISTINCT
        batches — otherwise score_history undo('any') would revert BOTH at once
        (the batches would collide at second precision). Microsecond precision +
        the suffix make same-tick collisions effectively impossible."""
    import uuid
    from datetime import datetime, timezone
    ts = datetime.now(timezone.utc).isoformat()
    return f"{ts}#{uuid.uuid4().hex[:8]}"


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
