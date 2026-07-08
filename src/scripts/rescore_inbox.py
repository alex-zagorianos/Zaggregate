"""Re-score every inbox row with the current scorer + active user_config. Pure
recompute (idempotent) — updates inbox.score / score_notes only, never fit.
Run after changing scoring logic or config. Use: py -m scripts.rescore_inbox [--dry-run]
"""
import json
import sqlite3
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import workspace
from match.scorer import salary_from_text, score_jobs
from models import JobResult
from tracker.db import current_db_path


def _cfg() -> dict:
    return workspace.load_config()


def _remote_ok() -> bool:
    """The same remote_ok context daily_run derives from preferences.json, so a
    rescore reproduces daily_run's scoring instead of stripping it."""
    try:
        import preferences
        return bool(preferences.load().get("hard", {}).get("remote_ok", True))
    except Exception:
        return True


def _remote_regions_ok() -> bool:
    """Mirror daily_run.py:404-408 -- remote_regions_ok is read from
    preferences.json's 'hard' block (default False), NOT from cfg. Threading it
    into the rescore keeps the region-remote handling daily_run applied at insert."""
    try:
        import preferences
        return bool(preferences.load().get("hard", {}).get("remote_regions_ok", False))
    except Exception:
        return False


def rescore(db_path=None, cfg=None, dry_run=False):
    db_path = db_path or current_db_path()
    cfg = cfg or _cfg()
    # Scoring keywords MUST match daily_run's: it scores with effective_keywords
    # (which derives a real set from `industry` when cfg['keywords'] is empty).
    # Reading cfg['keywords'] raw here made this pass title-blind for
    # industry-only projects and wiped the just-inserted scores every run.
    from search.keyword_strategy import effective_keywords
    kws = effective_keywords(cfg)
    loc, floor = cfg.get("location", ""), cfg.get("salary_min")
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM inbox").fetchall()
    cols = set(rows[0].keys()) if rows else set()

    before = [r["score"] for r in rows]
    pairs = []  # (row, job) so we survive score_jobs' in-place sort
    for r in rows:
        lo, hi = salary_from_text(r["salary_text"] or "")
        pairs.append((r, JobResult(
            title=r["title"], company=r["company"], location=r["location"] or "",
            salary_min=lo, salary_max=hi, description=r["description"] or "",
            url=r["url"] or "", source_keyword="", created=r["created"] or "",
            source_api=r["source"] or "",
            board_count=r["board_count"] if "board_count" in cols else -1,
        )))

    # Route through the ONE scoring path (score_jobs), which derives target_level
    # (exec adjustment) and semantic_profile itself, and pass remote_ok from
    # preferences. Previously this called score_job WITHOUT those three, silently
    # erasing the exec +/-15/16 adjustment daily_run applies at insert (P0#7).
    # It ALSO omitted the four S32 honesty levers (seniority_target / years_cap /
    # title_context_required from cfg, remote_regions_ok from preferences 'hard'),
    # so the over-target down-nudge, title-context cap, and region-remote handling
    # daily_run.py:409-419 applied at insert were silently reverted every run. Pass
    # all four here EXACTLY as daily_run does so daily-run-then-rescore is stable.
    # score_jobs SORTS in place, so we hold (row, job) pairs and read each job's
    # own .score/.score_notes back rather than relying on positional order.
    score_jobs(
        [j for _, j in pairs], keywords=kws, location=loc, salary_floor=floor,
        exclude_keywords=cfg.get("exclude_keywords", []),
        exclude_titles=cfg.get("exclude_titles"),
        title_miss_penalty=cfg.get("title_miss_penalty"),
        seniority_exclude=cfg.get("seniority_exclude"),
        remote_ok=_remote_ok(),
        seniority_target=cfg.get("seniority_target"),
        years_cap=cfg.get("years_cap"),
        remote_regions_ok=_remote_regions_ok(),
        title_context_required=cfg.get("title_context_required"),
        suggested_excludes=cfg.get("suggested_excludes"),
    )

    after = []
    miss = blocked = 0
    for r, job in pairs:
        sc, notes = job.score, job.score_notes
        after.append(sc)
        miss += "title-miss" in notes
        blocked += "excl-title" in notes
        if not dry_run:
            conn.execute("UPDATE inbox SET score=?, score_notes=? WHERE id=?",
                         (sc, notes, r["id"]))
    if not dry_run:
        conn.commit()
    conn.close()
    return {"n": len(rows), "before": before, "after": after,
            "title_miss": miss, "excl_title": blocked}


def _band(scores):
    lo = sum(1 for s in scores if s < 40)
    return (f"min/median/max {min(scores)}/{int(statistics.median(scores))}/{max(scores)}"
            f" | below 40: {lo}") if scores else "empty"


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    res = rescore(dry_run=dry)
    print(f"{'[dry-run] ' if dry else ''}re-scored {res['n']} inbox rows")
    print(f"  before: {_band(res['before'])}")
    print(f"  after : {_band(res['after'])}")
    print(f"  title-miss: {res['title_miss']} | excl-title: {res['excl_title']}")
