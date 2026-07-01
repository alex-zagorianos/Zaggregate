"""Headless morning search: query the free sources with user_config.json,
score everything, and drop never-seen jobs above DAILY_MIN_SCORE into the
tracker inbox. The GUI then opens to a ranked list of fresh matches.

Run:        py daily_run.py  [--user-config config_dad.json] [--min-score 40]
Schedule:   setup_schedule.bat   (Windows Task Scheduler, 07:30 daily)

jsearch is deliberately excluded (see DAILY_SOURCES in config.py) so the
200/month free tier survives manual searches.
"""
import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import workspace
from config import DAILY_MIN_SCORE, DAILY_SOURCES, DEFAULT_KEYWORDS, DEFAULT_LOCATION

# id of the open health-beacon run row for the current run, set in main() and
# read by run_main()'s except handler to close it 'failed'. None = no open run.
_RUN_ID = None


def log(msg: str):
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{stamp}] {msg}"
    print(line)
    try:
        with open(workspace.output_dir() / "daily_run.log", "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass  # logging must never kill the run


def main():
    parser = argparse.ArgumentParser(description="Headless daily job search -> inbox")
    parser.add_argument("--user-config", type=str, default=None)
    parser.add_argument("--project", type=str, default=None,
                        help="Run against this project workspace (default: active).")
    parser.add_argument("--min-score", type=int, default=None,
                        help=f"Inbox threshold (default: user_config or {DAILY_MIN_SCORE})")
    parser.add_argument("--max-pages", type=int, default=1)
    args = parser.parse_args()

    if args.project and not args.user_config:
        workspace.set_active(args.project)

    from search.cli import build_clients, load_user_config
    from search.search_engine import SearchEngine
    from match.scorer import score_jobs
    from tracker.db import (init_db, inbox_add_many, inbox_count,
                            record_run_start, record_run_finish)

    import userdata
    userdata.bootstrap()  # first-run: seed the data folder + runtime dirs

    # Open the health-beacon row before any work so a crash anywhere below is
    # attributable. init_db first so the runs table exists. run_main()'s
    # top-level except closes it 'failed'; the success path closes it 'ok'/'zero'.
    globals()["_RUN_ID"] = None  # clear any stale id from a prior in-process run
    init_db()
    run_project = args.project or workspace.active_slug() or ""
    run_id = record_run_start(run_project)
    globals()["_RUN_ID"] = run_id  # handed to run_main's except for the failed path

    cfg = load_user_config(args.user_config)
    keywords = cfg.get("keywords") or list(DEFAULT_KEYWORDS)
    location = cfg.get("location") or DEFAULT_LOCATION
    salary_min = int(cfg["salary_min"]) if cfg.get("salary_min") is not None else None
    min_score = args.min_score if args.min_score is not None else int(
        cfg.get("daily_min_score", DAILY_MIN_SCORE))

    cfg_sources = cfg.get("sources", {})
    sources = [s for s in DAILY_SOURCES if cfg_sources.get(s, True)]
    industry = cfg.get("industry") or None  # filters the careers registry

    # Broaden the QUERY keywords for API recall — job APIs phrase-match, so narrow
    # seniority-laden titles ("VP Clinical Informatics") return ~0 while the field
    # term ("clinical informatics") returns 20x more (measured 2026-07-01). The
    # ORIGINAL keywords stay the scoring/title-match set below; seniority is handled
    # in scoring/gate, not the query string. No-op for eng IC titles (Alex unchanged).
    from search.keyword_strategy import broad_query_keywords
    if cfg.get("broaden_keywords", True):
        query_keywords = broad_query_keywords(keywords, cfg.get("industry") or "")
    else:
        query_keywords = keywords

    log(f"daily_run start | sources={sources} | {len(keywords)} keywords "
        f"({len(query_keywords)} broadened for query) | "
        f"location={location} | min_score={min_score} | industry={industry}")

    # Preflight reach check: warn when the career-page (registry) path has almost
    # no employers for this field, so a near-zero 'careers' contribution is visible
    # up front instead of a mystery (the eng-only registry has ~0 health cos).
    if industry and "careers" in sources:
        try:
            from scrape.company_registry import industry_company_count
            n_reg = industry_company_count(industry)
            if n_reg < 10:
                log(f"NOTE: only {n_reg} registry companies match industry "
                    f"'{industry}' — the 'careers' path will add few/no jobs. Build "
                    f"your employer list (seed_companies.py / Add Companies / discovery).")
        except Exception:
            pass

    # Opt-in tiered scraping: as the registry grows, scrape only the boards "due"
    # this run (active boards every run, quiet/dead ones less often) so the daily
    # run stays fast. Off by default — the full registry is scraped as before.
    tiered = bool(cfg.get("tiered_scrape"))
    clients = build_clients(sources, cache_enabled=True, industry_filter=industry,
                            tiered_careers=tiered)
    if not clients:
        log("ABORT: no sources could be initialized (check .env).")
        # Don't leave the beacon row stuck 'running' — this is a failed run.
        record_run_finish(run_id, "failed",
                          error="no sources could be initialized (check .env)")
        sys.exit(1)

    results = SearchEngine(clients).run_full_search(
        keywords=query_keywords, location=location, salary_min=salary_min,
        max_pages_per_keyword=args.max_pages,
    )
    if tiered:
        for c in clients:
            if hasattr(c, "finalize_tiering"):
                c.finalize_tiering()
    # Preference hard-gate: drop jobs violating the user's hard constraints
    # (salary floor / location / dealbreakers) before scoring + inbox. No-op when
    # preferences.json is absent or permissive (a fresh data folder).
    import ranker
    _pre_gate = len(results)
    results = ranker.gate(results)
    if len(results) != _pre_gate:
        log(f"preferences hard-gate | {_pre_gate} -> {len(results)}")
    # Remote-acceptable jobs get full location credit (not 0) so they rank fairly
    # when the user is open to remote — honors preferences.json remote_ok.
    try:
        import preferences
        _remote_ok = bool(preferences.load().get("hard", {}).get("remote_ok", True))
    except Exception:
        _remote_ok = True
    score_jobs(results, keywords=keywords, location=location,
               salary_floor=salary_min,
               exclude_keywords=cfg.get("exclude_keywords", []),
               exclude_titles=cfg.get("exclude_titles"),
               title_miss_penalty=cfg.get("title_miss_penalty"),
               seniority_exclude=cfg.get("seniority_exclude"),
               remote_ok=_remote_ok)

    # Freshness deltas: mark jobs new since the last daily run for THIS project
    # (manual GUI/CLI searches don't move this baseline). Non-destructive — just
    # an annotation surfaced by the GUI "New only" filter and the log below.
    import search.freshness as freshness
    fresh_id = f"daily:{run_project or 'root'}"
    _prev_fresh = freshness.load_prev_keys(fresh_id)
    for r in results:
        r.is_new = r.job_key not in _prev_fresh

    qualified = [r for r in results if r.score >= min_score]

    # Per-company cap: mega boards (Anduril, SpaceX) can match 300+ postings a
    # run and drown everyone else. Enforced against the PERSISTED inbox inside
    # inbox_add_many (not per-run) so a board can't accrue cap rows every run and
    # pile up over N days. score_jobs sorted best-first, so each company keeps its
    # top matches. 0/None disables.
    cap = int(cfg.get("max_per_company", 15) or 0)

    # init_db already ran at the top (for the runs table); this is idempotent.
    init_db()
    before = inbox_count()
    new_batch = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    added = inbox_add_many(qualified, per_company_cap=cap, new_batch=new_batch)
    log(f"daily_run done | {len(results)} found | {len(qualified)} >= {min_score} | "
        f"{added} new -> inbox (inbox now {inbox_count()})")

    # Advance the freshness baseline to this run's found set, and report how many
    # of the inboxed jobs are new since the last run.
    freshness.save_keys(fresh_id, {r.job_key for r in results})
    n_new = sum(1 for r in qualified if r.is_new)
    log(f"freshness | {n_new} of {added} newly-inboxed are new since last run "
        f"(baseline '{fresh_id}' now {len(results)} keys)")

    # Re-score the whole inbox for this project with the current config so edited
    # keywords/salary don't leave stale, incomparable scores on older rows.
    # Cost: one extra full pass over the inbox per run (recompute only, no fit).
    try:
        from scripts.rescore_inbox import rescore
        rs = rescore(cfg=cfg)
        log(f"re-scored {rs['n']} inbox rows with current config")
    except Exception as e:  # re-score is best-effort; never fail the run for it
        log(f"WARN: inbox re-score skipped: {type(e).__name__}: {e}")

    # Optionally remove dead (404) inbox links each run. OFF by default: it
    # re-probes every career link (~1 network call/row), which materially slows a
    # scheduled run; the GUI "Clean dead links" button and `cli --prune-inbox`
    # cover the on-demand case. Opt in with "prune_inbox_daily": true in config.
    if cfg.get("prune_inbox_daily"):
        try:
            from scrape.inbox_health import prune_inbox
            removed = prune_inbox()
            log(f"pruned {len(removed)} dead inbox link(s)")
        except Exception as e:  # best-effort; never fail the run for a prune
            log(f"WARN: inbox prune skipped: {type(e).__name__}: {e}")

    # Optionally grow the company registry from Common Crawl on the scheduled run
    # (additive, user-wins). OFF by default — it's network-heavy and the funnel's
    # own docstring says "occasional, not per-search"; opt in with
    # "discover_on_daily": true (or run `cli --discover` by hand).
    if cfg.get("discover_on_daily"):
        try:
            from discover.funnel import run_funnel
            summary = run_funnel()
            log(f"discovery funnel: harvested {summary.get('harvested', 0)} -> "
                f"added {summary.get('added', 0)} board(s)")
        except Exception as e:  # best-effort; never fail the run for discovery
            log(f"WARN: discovery skipped: {type(e).__name__}: {e}")

    # Health beacon: 'zero' when nothing new landed, else 'ok', with per-source
    # counts of what the search returned this run.
    from collections import Counter
    source_counts = dict(Counter((r.source_api or "") for r in results))
    status = "zero" if added == 0 else "ok"
    record_run_finish(run_id, status, source_counts=source_counts)


def run_main() -> int:
    """Run main() with a top-level guard so a scheduled run never dies silently:
    any exception is logged (with traceback) to the project log and returns 1.
    Also closes the health-beacon run row as 'failed' with the traceback."""
    import traceback
    try:
        main()
        return 0
    except SystemExit as e:
        return int(e.code or 0)
    except Exception as e:
        tb = traceback.format_exc()
        log(f"FATAL: daily_run crashed: {type(e).__name__}: {e}")
        log(tb)
        # Close the beacon row opened in main() (if we got that far) as failed.
        run_id = globals().get("_RUN_ID")
        if run_id is not None:
            try:
                from tracker.db import record_run_finish
                record_run_finish(run_id, "failed", error=tb)
            except Exception:
                pass  # beacon bookkeeping must never mask the original failure
        return 1


if __name__ == "__main__":
    sys.exit(run_main())
