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
from datetime import datetime
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

    log(f"daily_run start | sources={sources} | {len(keywords)} keywords | "
        f"location={location} | min_score={min_score} | industry={industry}")

    clients = build_clients(sources, cache_enabled=True, industry_filter=industry)
    if not clients:
        log("ABORT: no sources could be initialized (check .env).")
        # Don't leave the beacon row stuck 'running' — this is a failed run.
        record_run_finish(run_id, "failed",
                          error="no sources could be initialized (check .env)")
        sys.exit(1)

    results = SearchEngine(clients).run_full_search(
        keywords=keywords, location=location, salary_min=salary_min,
        max_pages_per_keyword=args.max_pages,
    )
    score_jobs(results, keywords=keywords, location=location,
               salary_floor=salary_min,
               exclude_keywords=cfg.get("exclude_keywords", []),
               exclude_titles=cfg.get("exclude_titles"),
               title_miss_penalty=cfg.get("title_miss_penalty"),
               seniority_exclude=cfg.get("seniority_exclude"))

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
    added = inbox_add_many(qualified, per_company_cap=cap)  # skips seen + over-cap
    log(f"daily_run done | {len(results)} found | {len(qualified)} >= {min_score} | "
        f"{added} new -> inbox (inbox now {inbox_count()})")

    # Re-score the whole inbox for this project with the current config so edited
    # keywords/salary don't leave stale, incomparable scores on older rows.
    # Cost: one extra full pass over the inbox per run (recompute only, no fit).
    try:
        from scripts.rescore_inbox import rescore
        rs = rescore(cfg=cfg)
        log(f"re-scored {rs['n']} inbox rows with current config")
    except Exception as e:  # re-score is best-effort; never fail the run for it
        log(f"WARN: inbox re-score skipped: {type(e).__name__}: {e}")

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
