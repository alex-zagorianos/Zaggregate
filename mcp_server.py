"""Local stdio MCP server exposing the job-search engine to Claude Code / Desktop.

This is the "Claude Code channel": Claude Code itself is the ranker. The server is
a thin DATA layer over the engine + tracker.db (operating on the user's data
folder) — it does NOT call any AI. A typical find-jobs flow:

  get_preferences -> search_jobs -> list_inbox(unscored) -> [Claude ranks] ->
  set_fit_scores -> track_job (the best ones)

Run:  py mcp_server.py            (stdio transport; see claude-code/.mcp.json)
Requires the `mcp` package (official SDK; ships FastMCP). The data folder is
resolved by config (JOBPROGRAM_DATA env / ./data when frozen / repo root in dev).
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mcp.server.fastmcp import FastMCP

import userdata
import workspace
import preferences as prefs_mod
import ranker
from tracker import db
from tracker import service

mcp = FastMCP("jobscout")


@mcp.tool()
def get_preferences() -> dict:
    """Return the user's job preferences. Read this FIRST so your ranking reflects
    what they actually want: `profile_md` is their free-text description of ideal
    roles; `hard_filters` are constraints already enforced by search (salary floor,
    locations, deal-breakers)."""
    p = prefs_mod.load()
    return {"profile_md": p["profile_md"], "hard_filters": p["hard"]}


@mcp.tool()
def search_jobs(keywords: list[str] | None = None, location: str = "",
                max_pages: int = 1) -> dict:
    """Run a job search across the configured no-key + careers sources, apply the
    preferences hard-gate, score locally, and add new postings to the inbox.
    Defaults to the user's configured keywords/location. Returns counts; then call
    list_inbox to rank the new postings."""
    import config
    from search.cli import build_clients, load_user_config
    from search.search_engine import SearchEngine
    from match.scorer import score_jobs

    cfg = load_user_config()
    kws = keywords or cfg.get("keywords") or config.DEFAULT_KEYWORDS
    loc = location or cfg.get("location") or config.DEFAULT_LOCATION
    from search.keyword_strategy import gate_tech_sources
    sources = gate_tech_sources(config.DAILY_SOURCES, cfg.get("industry") or "",
                                cfg.get("sources", {}) or {})
    clients = build_clients(sources, cache_enabled=True,
                            industry_filter=cfg.get("industry"))
    if not clients:
        return {"error": "no sources could be initialized — check API keys."}

    results = SearchEngine(clients).run_full_search(
        keywords=kws, location=loc, salary_min=cfg.get("salary_min"),
        max_pages_per_keyword=max_pages)
    found = len(results)
    results = ranker.gate(results)                     # preferences hard-gate
    try:
        import preferences as _prefs
        _remote_regions_ok = bool(_prefs.load().get("hard", {}).get("remote_regions_ok", False))
    except Exception:
        _remote_regions_ok = False
    score_jobs(results, keywords=kws, location=loc,
               salary_floor=cfg.get("salary_min"),
               exclude_keywords=cfg.get("exclude_keywords", []),
               exclude_titles=cfg.get("exclude_titles"),
               title_miss_penalty=cfg.get("title_miss_penalty"),
               seniority_exclude=cfg.get("seniority_exclude"),
               seniority_target=cfg.get("seniority_target"),
               years_cap=cfg.get("years_cap"),
               remote_regions_ok=_remote_regions_ok,
               title_context_required=cfg.get("title_context_required"))
    db.init_db()
    added = db.inbox_add_many(
        results, per_company_cap=int(cfg.get("max_per_company", 15) or 0))
    return {"found": found, "after_hard_gate": len(results),
            "added_to_inbox": added, "inbox_total": db.inbox_count()}


@mcp.tool()
def list_inbox(limit: int = 20, unscored_only: bool = True,
               compact: bool = False) -> list[dict]:
    """List inbox postings for YOU to rank. limit=0 returns the ENTIRE inbox in
    one snapshot. Each row has id, title, company, location, salary, local
    `score`, current `fit` (-1 = unranked by you), your shortlist `rank` (-1 if
    not on it), the stable `job_key`, url, and (unless compact) a description
    snippet.

    compact=True replaces the description snippet with a one-line `facts` summary
    (~15x smaller) — use it to fit far more rows in your context. PAGE for large
    inboxes: keep `limit` at or below ~150 rows per call (raise the offset by
    re-listing after you've scored a batch) rather than pulling thousands of rows
    at once, which can overflow a small local model's window. Rank against
    preferences, then call set_fit_scores."""
    from tracker import service
    from rerank.schema import _job_key_for_row
    rows = db.inbox_all()
    out = []
    for r in rows:
        if unscored_only and (r.get("fit", -1) or -1) >= 0:
            continue
        row = {
            "id": r["id"], "title": r["title"], "company": r["company"],
            "location": r.get("location", ""), "salary": r.get("salary_text", ""),
            "score": r.get("score", -1), "fit": r.get("fit", -1),
            "rank": service.read_rank(r), "job_key": _job_key_for_row(r),
            "url": r.get("url", ""),
        }
        if compact:
            row["facts"] = _facts_summary_for_row(r)
        else:
            row["description"] = (r.get("description", "") or "")[:800]
        out.append(row)
        if limit and len(out) >= limit:   # limit=0 -> no cap (full snapshot)
            break
    return out


def _facts_summary_for_row(r: dict) -> str:
    """One-line facts summary for an inbox row (compact list_inbox). Best-effort:
    falls back to a short description snippet on any failure."""
    try:
        from models import JobResult
        from match.facts import facts_for, facts_summary
        j = JobResult(
            title=r.get("title", "") or "", company=r.get("company", "") or "",
            location=r.get("location", "") or "", salary_min=None, salary_max=None,
            description=r.get("description", "") or "", url=r.get("url", "") or "",
            source_keyword="", created=r.get("created", "") or "",
            source_api=r.get("source", "") or "")
        return facts_summary(facts_for(j))
    except Exception:
        return (r.get("description", "") or "")[:160]


@mcp.tool()
def set_fit_scores(scores: list[dict]) -> dict:
    """Persist YOUR preference-ranking back to the inbox. `scores` is a list of
    {"id", "fit": 0-100, "rationale": "<2-line why>", "rank"?: 1=best}. An
    optional `rank` marks the row as part of your recommended shortlist; ranked
    rows surface in the app's Top Picks tab. Returns how many were applied."""
    from tracker import service
    batch = service.new_rec_batch()
    applied = 0
    missed = 0
    for s in scores:
        try:
            iid = int(s["id"])
            landed = db.inbox_set_fit(iid, max(0, min(100, int(s["fit"]))),
                                      str(s.get("rationale", "")),
                                      source="mcp", batch=batch)
        except (KeyError, TypeError, ValueError):
            continue
        # Only count a score that ACTUALLY landed on a row — a nonexistent id is
        # a phantom, not an applied score (fixes the over-count bug). Same shared
        # batch + source='mcp' so Undo (scope='any') reverts the whole MCP set.
        if not landed:
            missed += 1
            continue
        applied += 1
        rank = s.get("rank")
        if rank is not None and str(rank).strip() != "":
            try:
                db.inbox_merge_extras(iid, service.rank_patch(int(rank), batch))
            except (TypeError, ValueError):
                pass
    return {"applied": applied, "missed": missed}


@mcp.tool()
def track_job(inbox_id: int) -> dict:
    """Promote an inbox posting to a tracked application (status=interested).
    Returns the new application id, or null if the row was already gone."""
    return {"application_id": db.inbox_track(int(inbox_id))}


@mcp.tool()
def dismiss_job(inbox_id: int) -> dict:
    """Dismiss an inbox posting so it won't resurface in future searches."""
    db.inbox_dismiss(int(inbox_id))
    return {"dismissed": int(inbox_id)}


@mcp.tool()
def export_inbox(out_dir: str, fmt: str = "both") -> dict:
    """Export the current inbox as the round-trip trio (ranking_export.csv +
    ranking_export.md + a versioned prompt.md) under out_dir, each row keyed by
    the stable job_key. Hand the CSV + prompt to any AI; it fills new_fit/
    new_rank/fit_rationale and you call import_scores with the returned file.
    fmt in {"both","csv","md"}. Returns the written paths as strings."""
    from rerank.export import export_inbox as _export
    paths = _export(db.inbox_all(), out_dir, fmt=fmt)
    out = {}
    for k, v in paths.items():
        out[k] = [str(p) for p in v] if isinstance(v, list) else str(v)
    return out


@mcp.tool()
def import_scores(path: str, policy: str = "overwrite") -> dict:
    """Import an AI-returned re-rank file (CSV or JSON) and re-rank the inbox.
    Validates the job_key join (unmatched rows are reported, never dropped),
    clamps new_fit to 0-100, snapshots prior scores to score_history (undoable),
    and applies the merge policy. policy in {"overwrite","keep_existing",
    "add_only"}. Returns {matched, updated, skipped, unmatched, errors}."""
    from rerank.import_ import import_scores as _import
    res = _import(path, service.inbox_rows_by_key(), policy=policy)
    return {"matched": res.matched, "updated": res.updated,
            "skipped": res.skipped, "unmatched": res.unmatched,
            "errors": res.errors}


# ── Application cycle (vision #4: help doesn't end when a job is tracked) ──────

def _days_since(iso_date: str) -> int | None:
    """Whole days from an ISO date string to today, or None if unparseable/blank."""
    from datetime import date, datetime
    s = (iso_date or "").strip()
    if not s:
        return None
    try:
        d = datetime.fromisoformat(s).date() if "T" in s else date.fromisoformat(s[:10])
    except ValueError:
        return None
    return (date.today() - d).days


def _app_days_in_stage(app_id: int, fallback_added: str) -> int | None:
    """Days since the application last CHANGED status (latest status_history row),
    falling back to date_added when there's no transition yet."""
    with db.get_conn() as conn:
        row = conn.execute(
            "SELECT changed_at FROM status_history WHERE job_id=? "
            "ORDER BY changed_at DESC LIMIT 1", (app_id,)).fetchone()
    return _days_since(row["changed_at"] if row else fallback_added)


@mcp.tool()
def list_applications(status: str | None = None) -> list[dict]:
    """List tracked applications (the pipeline), newest first. Optional `status`
    filters to one stage (interested/applied/phone_screen/interview/offer/
    rejected/withdrawn). Each row has id, title, company, status, date_applied,
    follow_up_date, and url. Use get_application for the full record."""
    rows = db.get_all(status if status else None)
    return [{"id": r["id"], "title": r["title"], "company": r["company"],
             "status": r.get("status", ""), "date_applied": r.get("date_applied", ""),
             "follow_up_date": r.get("follow_up_date", ""), "url": r.get("url", "")}
            for r in rows]


@mcp.tool()
def get_application(app_id: int) -> dict:
    """Full record for one tracked application: the saved JD `description`,
    `resume_path` (generated resume, if any), status, dates, contact, and
    `days_in_stage` (days since its last status change). Null if no such id."""
    r = db.get_job(int(app_id))
    if not r:
        return {"error": f"no application {app_id}"}
    r["days_in_stage"] = _app_days_in_stage(int(app_id), r.get("date_added", ""))
    return r


@mcp.tool()
def set_status(app_id: int, status: str) -> dict:
    """Advance an application to a new pipeline stage. Valid statuses (only):
    interested, applied, phone_screen, interview, offer, accepted, rejected,
    withdrawn, ghosted. Recording status='applied' stamps date_applied + arms
    the follow-up engine (via db.update_job). Returns the applied status, or
    {'error': ...} for an unknown status (nothing is written)."""
    status = (status or "").strip().lower()
    if status not in db.STATUSES:
        return {"error": f"unknown status {status!r}; valid: {list(db.STATUSES)}"}
    if not db.get_job(int(app_id)):
        return {"error": f"no application {app_id}"}
    db.update_job(int(app_id), status=status)
    return {"id": int(app_id), "status": status}


@mcp.tool()
def set_follow_up(app_id: int, date: str) -> dict:
    """Set/clear the next-action date on an application (ISO YYYY-MM-DD; ''
    clears). Surfaces the app in followups_due once the date arrives. Returns
    {'error': ...} for an unknown app_id (nothing is written)."""
    if not db.get_job(int(app_id)):
        return {"error": f"no application {app_id}"}
    db.update_job(int(app_id), follow_up_date=date)
    return {"id": int(app_id), "follow_up_date": date}


@mcp.tool()
def followups_due(within_days: int = 0) -> list[dict]:
    """Applications needing attention now (follow-ups due today/overdue, plus
    approaching deadlines). `within_days` widens the window. Each row carries
    due_kind ('follow-up'|'deadline') and due_date, soonest first."""
    rows = db.followups_due(within_days=int(within_days))
    return [{"id": r["id"], "title": r["title"], "company": r["company"],
             "status": r.get("status", ""), "due_kind": r.get("due_kind", ""),
             "due_date": r.get("due_date", "")} for r in rows]


@mcp.tool()
def funnel() -> dict:
    """The application funnel: counts per pipeline stage + totals, so you can see
    where things stand (e.g. how many applied vs interviewing)."""
    return db.get_counts()


@mcp.tool()
def draft_followup_context(app_id: int) -> dict:
    """Everything you need to DRAFT a follow-up email for a tracked application:
    the job (title/company/url), a JD snapshot (description), date_applied,
    days_since_applied, the recorded contact, and the current status. Returns an
    error dict if there's no such id. YOU write the email; this just gathers the
    context."""
    r = db.get_job(int(app_id))
    if not r:
        return {"error": f"no application {app_id}"}
    return {
        "id": r["id"], "title": r.get("title", ""), "company": r.get("company", ""),
        "url": r.get("url", ""), "status": r.get("status", ""),
        "date_applied": r.get("date_applied", ""),
        "days_since_applied": _days_since(r.get("date_applied", "")),
        "contact": r.get("contact", ""),
        "jd_snapshot": (r.get("description", "") or "")[:2000],
    }


# ── Resume tailoring over the cycle (feeds skillgap['missing'] into the prompt) ─

@mcp.tool()
def get_resume_prompt(inbox_id: int | None = None,
                      app_id: int | None = None) -> dict:
    """Build a resume+cover-letter prompt tailored to ONE job — an inbox posting
    (`inbox_id`) or a tracked application (`app_id`). The prompt folds the
    candidate's experience together with the JD's skill-gap 'missing' terms so
    tailoring targets what the posting actually asks for. Draft the resume by
    answering the prompt as the structured JSON it requests, then call
    save_resume. Returns {"prompt", "company"}."""
    from resume import service as rsvc
    if inbox_id is not None:
        rows = {r["id"]: r for r in db.inbox_all()}
        row = rows.get(int(inbox_id))
    elif app_id is not None:
        row = db.get_job(int(app_id))
    else:
        return {"error": "pass inbox_id or app_id"}
    if not row:
        return {"error": "no such job"}
    return {"prompt": rsvc.resume_prompt_for_row(row),
            "company": row.get("company", "")}


@mcp.tool()
def save_resume(data_json: str, company: str = "") -> dict:
    """Persist a tailored resume you drafted (the structured resume JSON matching
    get_resume_prompt's schema) as DOCX files. `data_json` is that JSON (string);
    `company` names the output files. Returns {"resume_path", "cover_path"}."""
    import json as _json
    from resume import service as rsvc
    try:
        data = _json.loads(data_json) if isinstance(data_json, str) else data_json
    except (ValueError, TypeError) as e:
        return {"error": f"bad data_json: {e}"}
    try:
        resume_path, cover_path = rsvc.save_resume_docx(data, company=company)
    except Exception as e:
        return {"error": f"could not build resume: {type(e).__name__}: {e}"}
    return {"resume_path": str(resume_path), "cover_path": str(cover_path)}


@mcp.tool()
def skill_gap(inbox_id: int) -> dict:
    """Offline skill-gap for one inbox posting: {"matched": [...], "missing": [...]}
    — the candidate's skills the JD mentions vs. the concrete terms the JD asks
    for that they can't yet claim. Zero AI, deterministic. Use it to steer a
    resume (get_resume_prompt already folds 'missing' in) or to explain a fit."""
    from match.skillgap import skill_gap as _gap
    rows = {r["id"]: r for r in db.inbox_all()}
    row = rows.get(int(inbox_id))
    if not row:
        return {"error": f"no inbox row {inbox_id}"}
    return _gap(row.get("description", "") or "")


def _parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="jobscout MCP stdio server")
    parser.add_argument("--project", type=str, default=None,
                        help="Serve this project workspace (default: active). "
                             "Pinned once at startup so a GUI project switch "
                             "mid-session can't redirect our writes.")
    return parser.parse_args(argv)


def main(argv=None) -> None:
    args = _parse_args(argv)
    userdata.bootstrap()   # seed the data folder before serving
    if args.project:
        known = {p["slug"] for p in workspace.list_projects()}
        if args.project not in known:
            raise SystemExit(f"unknown project: {args.project!r} "
                             f"(known: {sorted(known) or 'none'})")
    # Pin the active project ONCE at startup. A long-lived MCP session resolves
    # db/config/output paths per-call from projects.json, so without this a GUI
    # project switch (or a concurrent run) mid-session would silently redirect
    # our inbox/config writes into a DIFFERENT project (the S27 corruption
    # class). Pin the explicit --project, else whatever is active right now.
    workspace.pin_active(args.project or workspace.active_slug())
    db.init_db()
    mcp.run()              # stdio transport


if __name__ == "__main__":
    main()
