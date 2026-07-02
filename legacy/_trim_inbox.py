"""One-time inbox trim — retroactively apply the per-company cap to legacy
rows inserted before daily_run.py grew its cap (the 959 pre-Session-8 rows:
Anduril 311, SpaceX 188, etc.).

Keeps each company's top `max_per_company` rows by fit-else-score (the same
rank inbox_all uses); the rest are DISMISSED (url added to the dismissed
table), not just deleted, so the next daily run can't re-import them.

Usage:
    py _trim_inbox.py            # dry run — shows what would be trimmed
    py _trim_inbox.py --apply    # actually dismiss the excess rows

Delete this file after running.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from tracker.db import get_conn, init_db, normalize_url

CAP = 15
try:
    _cfg = json.loads((Path(__file__).parent / "user_config.json")
                      .read_text(encoding="utf-8"))
    CAP = int(_cfg.get("max_per_company", CAP)) or CAP
except Exception:
    pass

apply = "--apply" in sys.argv

init_db()
_RANK = "CASE WHEN fit >= 0 THEN fit ELSE score END"
with get_conn() as conn:
    rows = conn.execute(
        f"""SELECT id, url, company,
                   ROW_NUMBER() OVER (PARTITION BY company
                       ORDER BY {_RANK} DESC, date_added DESC) AS rk
            FROM inbox"""
    ).fetchall()

total = len(rows)
excess = [r for r in rows if r["rk"] > CAP]
by_co: dict[str, int] = {}
for r in excess:
    by_co[r["company"]] = by_co.get(r["company"], 0) + 1

print(f"Inbox: {total} rows; cap {CAP}/company -> "
      f"{len(excess)} rows over cap across {len(by_co)} companies")
for co, n in sorted(by_co.items(), key=lambda kv: -kv[1]):
    print(f"  {co}: -{n}")

if not excess:
    print("Nothing to trim.")
    sys.exit(0)

if not apply:
    print("\nDRY RUN — re-run with --apply to dismiss these rows.")
    sys.exit(0)

now = datetime.now(timezone.utc).isoformat()
with get_conn() as conn:
    conn.executemany(
        "INSERT OR IGNORE INTO dismissed (url, dismissed_at) VALUES (?,?)",
        [(normalize_url(r["url"]), now) for r in excess if r["url"]])
    conn.executemany("DELETE FROM inbox WHERE id=?",
                     [(r["id"],) for r in excess])
    conn.commit()
print(f"Done: dismissed {len(excess)} rows; inbox now {total - len(excess)}.")
