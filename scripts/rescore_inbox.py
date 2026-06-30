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
from match.scorer import salary_from_text, score_job
from models import JobResult
from tracker.db import current_db_path


def _cfg() -> dict:
    return workspace.load_config()


def rescore(db_path=None, cfg=None, dry_run=False):
    db_path = db_path or current_db_path()
    cfg = cfg or _cfg()
    kws, loc, floor = cfg.get("keywords", []), cfg.get("location", ""), cfg.get("salary_min")
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM inbox").fetchall()
    cols = set(rows[0].keys()) if rows else set()

    before = [r["score"] for r in rows]
    after = []
    miss = blocked = 0
    for r in rows:
        lo, hi = salary_from_text(r["salary_text"] or "")
        job = JobResult(
            title=r["title"], company=r["company"], location=r["location"] or "",
            salary_min=lo, salary_max=hi, description=r["description"] or "",
            url=r["url"] or "", source_keyword="", created=r["created"] or "",
            source_api=r["source"] or "",
            board_count=r["board_count"] if "board_count" in cols else -1,
        )
        sc, notes = score_job(
            job, keywords=kws, location=loc, salary_floor=floor,
            exclude_keywords=cfg.get("exclude_keywords", []),
            exclude_titles=cfg.get("exclude_titles"),
            title_miss_penalty=cfg.get("title_miss_penalty"),
            seniority_exclude=cfg.get("seniority_exclude"),
        )
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
