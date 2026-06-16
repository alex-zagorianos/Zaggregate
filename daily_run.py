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
    from tracker.db import init_db, inbox_add_many, inbox_count

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
    # run and drown everyone else. score_jobs sorted best-first, so this keeps
    # each company's top-K. 0/None disables.
    cap = int(cfg.get("max_per_company", 15) or 0)
    if cap > 0:
        from collections import defaultdict
        per_company: dict[str, int] = defaultdict(int)
        capped = []
        for r in qualified:
            key = (r.company or "").lower().strip()
            per_company[key] += 1
            if per_company[key] <= cap:
                capped.append(r)
        if len(capped) < len(qualified):
            log(f"per-company cap {cap}: {len(qualified)} -> {len(capped)} "
                f"(trimmed {len(qualified) - len(capped)})")
        qualified = capped

    init_db()
    added = inbox_add_many(qualified)  # skips tracked/dismissed/already-inboxed
    log(f"daily_run done | {len(results)} found | {len(qualified)} >= {min_score} | "
        f"{added} new -> inbox (inbox now {inbox_count()})")


def run_main() -> int:
    """Run main() with a top-level guard so a scheduled run never dies silently:
    any exception is logged (with traceback) to the project log and returns 1."""
    import traceback
    try:
        main()
        return 0
    except SystemExit as e:
        return int(e.code or 0)
    except Exception as e:
        log(f"FATAL: daily_run crashed: {type(e).__name__}: {e}")
        log(traceback.format_exc())
        return 1


if __name__ == "__main__":
    sys.exit(run_main())
