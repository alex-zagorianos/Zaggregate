"""One-time (idempotent) backfill: rewrite Greenhouse inbox links to the
server-rendered hosted application URL.

Greenhouse's `absolute_url` is often the company's own JavaScript careers SPA,
which for some tenants (Nuro, Tulip, Aurora, Zipline, …) never renders the
specific job — the link looks dead. We rewrite every Greenhouse-identifiable
inbox row to `job-boards.greenhouse.io/embed/job_app?for={slug}&token={id}`,
which renders the job + apply form server-side for ALL boards. This also makes
existing rows converge with new scrapes (the scraper now emits the same URL), so
re-runs don't create duplicates.

Slugs: hosted-path links carry the slug; company-embed `gh_jid` links don't, so
the slug is resolved from the company name via the registry. Unresolvable rows
are left untouched. Safe to re-run (idempotent).

Run: py -m scripts.fix_greenhouse_urls [--dry-run] [--all-projects]
"""
import sqlite3
import sys
from pathlib import Path
from typing import Callable, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from models import normalize_url
from scrape.greenhouse_url import embed_url, parse
from tracker.db import current_db_path


def _default_resolver() -> Callable[[str], Optional[str]]:
    """company-name (lowercased) -> greenhouse slug, from the merged registry."""
    from scrape.company_registry import get_registry
    m = {e.name.lower(): e.slug for e in get_registry() if e.ats_type == "greenhouse"}
    return m.get


def fix(db_path=None, dry_run: bool = False,
        resolve_slug: Optional[Callable[[str], Optional[str]]] = None) -> tuple[int, int, int]:
    """Returns (fixed, skipped, dropped_duplicates) for one inbox DB."""
    db_path = db_path or current_db_path()
    resolve_slug = resolve_slug or _default_resolver()
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT id, norm_url, company, url FROM inbox").fetchall()

    fixed = skipped = dropped = 0
    for r in rows:
        g = parse(r["url"])
        if g is None:
            skipped += 1                         # not a Greenhouse link
            continue
        slug = g[0] or resolve_slug((r["company"] or "").lower())
        if not slug:
            skipped += 1                         # company-embed link, slug unknown
            continue
        new_url = embed_url(slug, g[1])
        new_norm = normalize_url(new_url)
        if new_norm == r["norm_url"]:
            skipped += 1                         # already canonical
            continue
        if dry_run:
            fixed += 1
            continue
        try:
            conn.execute("UPDATE inbox SET url=?, norm_url=? WHERE id=?",
                         (new_url, new_norm, r["id"]))
            fixed += 1
        except sqlite3.IntegrityError:
            # A canonical row for this posting already exists; drop the stale dupe.
            conn.execute("DELETE FROM inbox WHERE id=?", (r["id"],))
            dropped += 1
    conn.commit()
    conn.close()
    return fixed, skipped, dropped


def _all_project_dbs() -> list[tuple[str, Path]]:
    import workspace
    out = []
    for p in workspace.list_projects():
        db = workspace.db_path(p["slug"])
        if Path(db).exists():
            out.append((p["slug"], Path(db)))
    return out


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    tag = "[dry-run] would fix" if dry else "fixed"
    if "--all-projects" in sys.argv:
        targets = _all_project_dbs()
    else:
        targets = [("(active)", current_db_path())]
    grand = [0, 0, 0]
    for slug, db in targets:
        f, s, d = fix(db_path=db, dry_run=dry)
        grand[0] += f; grand[1] += s; grand[2] += d
        print(f"  {slug:24s} {tag} {f} | skipped {s} | dropped duplicates {d}")
    print(f"TOTAL: {tag} {grand[0]} | skipped {grand[1]} | dropped duplicates {grand[2]}")
