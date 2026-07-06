"""One-time (idempotent) backfill: repair Workday inbox URLs that were stored
without the site segment (host+externalPath -> 404). Inserts the site so links
resolve, e.g. .../job/X -> .../CaterpillarCareers/job/X. Safe to re-run; only
touches rows that are still site-less. Run: py -m scripts.fix_workday_urls [--dry-run] [--project SLUG]
"""
import argparse
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scrape.company_registry import get_registry
from scrape.workday_scraper import _job_url
from tracker.db import current_db_path, normalize_url

_WD = re.compile(r"https://(?P<t>[^.]+)\.wd(?P<n>\d+)\.myworkdayjobs\.com(?P<path>/.*)$")


def _site_map() -> dict[tuple[str, str], str]:
    m: dict[tuple[str, str], str] = {}
    for e in get_registry():
        if e.ats_type == "workday" and e.slug.count(":") == 2:
            t, n, site = e.slug.split(":")
            m[(t, n)] = site
    return m


def fix(db_path=None, dry_run=False) -> tuple[int, int, int]:
    """Returns (fixed, skipped, dropped_duplicates)."""
    db_path = db_path or current_db_path()
    sites = _site_map()
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, url FROM inbox WHERE url LIKE '%myworkdayjobs.com/%'"
    ).fetchall()
    fixed = skipped = dropped = 0
    for r in rows:
        m = _WD.match(r["url"])
        site = sites.get((m["t"], m["n"])) if m else None
        if not site:
            skipped += 1
            continue
        new_url = _job_url(m["t"], m["n"], site, m["path"])
        if new_url == r["url"]:
            skipped += 1            # already has its site segment
            continue
        if dry_run:
            fixed += 1
            continue
        try:
            conn.execute("UPDATE inbox SET url=?, norm_url=? WHERE id=?",
                         (new_url, normalize_url(new_url), r["id"]))
            fixed += 1
        except sqlite3.IntegrityError:
            # A correctly-URL'd row for this posting already exists; drop the dupe.
            conn.execute("DELETE FROM inbox WHERE id=?", (r["id"],))
            dropped += 1
    conn.commit()
    conn.close()
    return fixed, skipped, dropped


if __name__ == "__main__":
    import workspace
    ap = argparse.ArgumentParser(description="Repair Workday inbox URLs.")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--project", default=None,
                    help="Operate on this project (default: active). Pinned "
                         "once so a concurrent switch can't move our target DB.")
    args = ap.parse_args()

    # Resolve + pin the target project ONCE for the whole run so a concurrent
    # GUI switch / daily_run can't redirect current_db_path() mid-run.
    workspace.pin_active(args.project or workspace.active_slug())
    f, s, d = fix(dry_run=args.dry_run)
    tag = "[dry-run] would fix" if args.dry_run else "fixed"
    print(f"{tag} {f} | skipped {s} | dropped duplicates {d}")
