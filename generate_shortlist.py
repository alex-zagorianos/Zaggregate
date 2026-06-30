import csv, glob
from pathlib import Path
from datetime import date

BASE = Path(r"E:\ClaudeWork\ZAG0005 - Job Search App\projects")
OUT = Path(r"E:\ClaudeWork\ZAG0005 - Job Search App\job search\SHORTLIST-2026-06-19.md")
LANES = ["controls", "software", "applied-ai"]

def g(d, *names):
    for n in names:
        for k in d:
            if k.strip().lower() == n:
                return (d[k] or "").strip()
    return ""

best = {}  # (title.lower, company.lower) -> row dict
for lane in LANES:
    files = sorted(glob.glob(str(BASE / lane / "output" / "job_search_*.csv")))
    if not files:
        continue
    with open(files[-1], encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            title, company = g(r, "title"), g(r, "company")
            if not title or not company:
                continue
            try:
                sc = float(g(r, "score") or 0)
            except Exception:
                sc = 0.0
            key = (title.lower(), company.lower())
            rec = {"score": sc, "title": title, "company": company,
                   "location": g(r, "location"), "url": g(r, "url"),
                   "smin": g(r, "salary_min"), "smax": g(r, "salary_max"),
                   "lane": lane}
            if key not in best or sc > best[key]["score"]:
                best[key] = rec
            best[key].setdefault("lanes", set()).add(lane)

rows = sorted(best.values(), key=lambda x: x["score"], reverse=True)

def sal(r):
    a, b = r["smin"], r["smax"]
    def fmt(v):
        try: return f"${int(float(v)):,}"
        except: return ""
    a, b = fmt(a), fmt(b)
    return f"{a}-{b}" if a and b else (a or b or "—")

def bucket(loc):
    l = loc.lower()
    if "cincinnati" in l or "hamilton" in l: return "Cincinnati"
    if "ohio" in l or "columbus" in l or ", oh" in l: return "Ohio"
    if "remote" in l: return "Remote"
    return "National / Relocate"

groups = {"Cincinnati": [], "Ohio": [], "Remote": [], "National / Relocate": []}
for r in rows:
    groups[bucket(r["location"])].append(r)

lines = [f"# Job Shortlist — {date.today().isoformat()}",
         "",
         "From a live run of the `controls` / `software` / `applied-ai` lanes (deduped vs tracker). "
         "Scored against the profile; senior roles surface high on keyword match but may want 5+ yrs — "
         "treat those as stretch. Salaries are parser-extracted; verify on the posting.",
         ""]
for grp in ["Cincinnati", "Ohio", "Remote", "National / Relocate"]:
    items = groups[grp][:12]
    if not items:
        continue
    lines.append(f"## {grp}")
    lines.append("")
    for r in items:
        lanes = "+".join(sorted(r.get("lanes", {r['lane']})))
        lines.append(f"- **[{int(r['score'])}]** {r['title']} — **{r['company']}** "
                     f"· {r['location']} · {sal(r)} · _{lanes}_  \n  {r['url']}")
    lines.append("")

OUT.write_text("\n".join(lines), encoding="utf-8")
print(f"Wrote {OUT}")
print(f"Unique roles: {len(rows)} | Cincinnati: {len(groups['Cincinnati'])} | "
      f"Ohio: {len(groups['Ohio'])} | Remote: {len(groups['Remote'])} | "
      f"National: {len(groups['National / Relocate'])}")
print("\nTOP 10 OVERALL:")
for r in rows[:10]:
    print(f"  [{int(r['score'])}] {r['title'][:48]:48} | {r['company'][:22]:22} | {r['location'][:22]:22} | {sal(r)}")
