import csv, glob, os
from pathlib import Path

BASE = Path(r"E:\ClaudeWork\ZAG0005 - Job Search App\projects")
LANES = ["controls", "software", "applied-ai"]

def pick(d, *names):
    for n in names:
        for k in d:
            if k.strip().lower() == n:
                return (d[k] or "").strip()
    return ""

for lane in LANES:
    files = sorted(glob.glob(str(BASE / lane / "output" / "job_search_*.csv")))
    if not files:
        print(f"\n### {lane}: no CSV\n"); continue
    f = files[-1]
    with open(f, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    def score(r):
        try: return float(pick(r, "score", "match score", "match_score") or 0)
        except: return 0.0
    rows.sort(key=score, reverse=True)
    print(f"\n{'='*70}\n### {lane.upper()}  —  {len(rows)} scored rows  ({os.path.basename(f)})\n{'='*70}")
    if rows:
        print("COLUMNS:", list(rows[0].keys()))
    seen = set()
    shown = 0
    for r in rows:
        title = pick(r, "title")
        company = pick(r, "company")
        key = (title.lower(), company.lower())
        if key in seen:  # collapse same role surfaced by multiple keywords
            continue
        seen.add(key)
        sc = pick(r, "score", "match score", "match_score")
        loc = pick(r, "location")
        sal = pick(r, "salary", "salary range", "salary_range", "salary_min")
        src = pick(r, "source")
        print(f"[{sc:>3}] {title[:52]:52} | {company[:24]:24} | {loc[:20]:20} | {sal[:18]:18} | {src}")
        shown += 1
        if shown >= 18:
            break
