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
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mcp.server.fastmcp import FastMCP

import userdata
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
    clients = build_clients(config.DAILY_SOURCES, cache_enabled=True,
                            industry_filter=cfg.get("industry"))
    if not clients:
        return {"error": "no sources could be initialized — check API keys."}

    results = SearchEngine(clients).run_full_search(
        keywords=kws, location=loc, salary_min=cfg.get("salary_min"),
        max_pages_per_keyword=max_pages)
    found = len(results)
    results = ranker.gate(results)                     # preferences hard-gate
    score_jobs(results, keywords=kws, location=loc,
               salary_floor=cfg.get("salary_min"),
               exclude_keywords=cfg.get("exclude_keywords", []),
               exclude_titles=cfg.get("exclude_titles"),
               title_miss_penalty=cfg.get("title_miss_penalty"),
               seniority_exclude=cfg.get("seniority_exclude"))
    db.init_db()
    added = db.inbox_add_many(
        results, per_company_cap=int(cfg.get("max_per_company", 15) or 0))
    return {"found": found, "after_hard_gate": len(results),
            "added_to_inbox": added, "inbox_total": db.inbox_count()}


@mcp.tool()
def list_inbox(limit: int = 20, unscored_only: bool = True) -> list[dict]:
    """List inbox postings for YOU to rank. limit=0 returns the ENTIRE inbox in
    one snapshot — use it to see ALL relevant jobs before picking a top-X. Each
    row has id, title, company, location, salary, local `score`, current `fit`
    (-1 = unranked by you), your shortlist `rank` (-1 if not on it), the stable
    `job_key`, url, and a description snippet. Rank against preferences, then
    call set_fit_scores."""
    from tracker import service
    from rerank.schema import _job_key_for_row
    rows = db.inbox_all()
    out = []
    for r in rows:
        if unscored_only and (r.get("fit", -1) or -1) >= 0:
            continue
        out.append({
            "id": r["id"], "title": r["title"], "company": r["company"],
            "location": r.get("location", ""), "salary": r.get("salary_text", ""),
            "score": r.get("score", -1), "fit": r.get("fit", -1),
            "rank": service.read_rank(r), "job_key": _job_key_for_row(r),
            "url": r.get("url", ""),
            "description": (r.get("description", "") or "")[:800],
        })
        if limit and len(out) >= limit:   # limit=0 -> no cap (full snapshot)
            break
    return out


@mcp.tool()
def set_fit_scores(scores: list[dict]) -> dict:
    """Persist YOUR preference-ranking back to the inbox. `scores` is a list of
    {"id", "fit": 0-100, "rationale": "<2-line why>", "rank"?: 1=best}. An
    optional `rank` marks the row as part of your recommended shortlist; ranked
    rows surface in the app's Top Picks tab. Returns how many were applied."""
    from tracker import service
    batch = service.new_rec_batch()
    applied = 0
    for s in scores:
        try:
            iid = int(s["id"])
            db.inbox_set_fit(iid, max(0, min(100, int(s["fit"]))),
                             str(s.get("rationale", "")))
        except (KeyError, TypeError, ValueError):
            continue
        applied += 1
        rank = s.get("rank")
        if rank is not None and str(rank).strip() != "":
            try:
                db.inbox_merge_extras(iid, service.rank_patch(int(rank), batch))
            except (TypeError, ValueError):
                pass
    return {"applied": applied}


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
    return {k: str(v) for k, v in paths.items()}


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


def main() -> None:
    userdata.bootstrap()   # seed the data folder before serving
    db.init_db()
    mcp.run()              # stdio transport


if __name__ == "__main__":
    main()
