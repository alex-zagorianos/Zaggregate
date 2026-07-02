"""Migrate parked Workday rows in companies.json to the public `workday_cxs`
reader (S32 — the marquee-employer unlock).

The wave-1 `workday_cxs_scraper` recovers CSRF-*disabled* Workday tenants
(Caterpillar, Marsh McLennan, NVIDIA, Adobe, ...) by POSTing the public
`wday/cxs` JSON search — the documented read path that dodges the HTML/CSRF wall
the legacy "workday" GET-prime path hit with HTTP 422. Cloudflare/Akamai-fronted
tenants (FedEx, AutoZone, Banner, PACCAR, ...) still 422 a plain client and stay
un-pullable. So the clean, general path (per the wave-1 builder's recommendation)
is: scan companies.json for rows that POINT AT a myworkdayjobs.com board but are
typed 'direct' (parked, never scraped) or legacy 'workday', LIVE re-probe each
via the production `workday_cxs` fetcher, and relabel to `workday_cxs` ONLY the
ones that actually return jobs. A row that 422s / is dead / returns 0 is left
EXACTLY as it was — the migration never breaks a working row and never resurrects
a walled one.

    py -m scripts.migrate_workday_cxs                 # dry-run (default), report only
    py -m scripts.migrate_workday_cxs --apply         # write the relabels
    py -m scripts.migrate_workday_cxs --json path.json --limit 20

The slug format is identical between "workday", "direct"(myworkdayjobs URL) and
"workday_cxs" once derived — "tenant:N:site" — so relabeling is a pure ats_type
change plus (for a 'direct' row) swapping the full URL slug for the derived
tenant slug. Atomic write via the same write_cache the registry uses, preserving
the file's comments/examples and byte format.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scrape.ats_detect import probe_count
from scrape.company_registry import CompanyEntry
from scrape.workday_cxs_scraper import derive_slug


def _is_workday_url(s: str) -> bool:
    return "myworkdayjobs.com" in (s or "").lower()


def _target_slug(ats_type: str, slug: str) -> str:
    """The 'tenant:N:site' slug a row should carry as workday_cxs, or '' if the
    row can't be resolved to one. A legacy 'workday' row already stores that slug;
    a 'direct' row stores the full careers URL, so derive it."""
    slug = (slug or "").strip()
    if slug.count(":") == 2 and not _is_workday_url(slug):
        # Already the tenant:N:site identity (legacy 'workday' rows).
        return slug
    if _is_workday_url(slug):
        return derive_slug(slug)
    return ""


def _candidates(companies: list[dict]) -> list[dict]:
    """The companies.json records eligible for migration: a myworkdayjobs board
    typed 'direct', or any legacy 'workday' row. Skips already-migrated
    'workday_cxs' rows and every non-Workday row."""
    out = []
    for c in companies:
        if "_example" in c or not c.get("name"):
            continue
        ats = (c.get("ats_type") or "").strip().lower()
        slug = c.get("slug") or ""
        if ats == "workday":
            out.append(c)                                   # legacy path -> re-probe
        elif ats == "direct" and _is_workday_url(slug):
            out.append(c)                                   # parked Workday careers URL
    return out


def migrate(json_path: Path, *, apply: bool = False, limit: int | None = None,
            probe: bool = True) -> dict:
    """Scan + live-probe the Workday candidates in `json_path`. Returns a report
    dict; writes the file only when apply=True. A row is relabeled to
    'workday_cxs' ONLY when its live probe returns >0 jobs — everything else is
    left byte-identical."""
    try:
        raw = json.loads(json_path.read_text(encoding="utf-8")) if json_path.exists() else {}
    except Exception as e:
        return {"error": f"could not read {json_path.name}: {e}", "rows": []}
    if not isinstance(raw, dict):
        return {"error": f"{json_path.name} is not a JSON object", "rows": []}

    companies = raw.get("companies", [])
    cands = _candidates(companies)
    if limit is not None:
        cands = cands[:limit]

    rows: list[dict] = []
    migrated = 0
    for c in cands:
        name = c.get("name", "")
        ats = (c.get("ats_type") or "").strip().lower()
        old_slug = c.get("slug") or ""
        target = _target_slug(ats, old_slug)
        if not target:
            rows.append({"name": name, "from": ats, "slug": old_slug,
                         "count": None, "action": "skip",
                         "detail": "no derivable tenant slug"})
            continue

        if probe:
            entry = CompanyEntry(name=name, ats_type="workday_cxs", slug=target,
                                 industries=list(c.get("industries") or []))
            n = probe_count(entry)
        else:
            n = None

        if n and n > 0:
            rows.append({"name": name, "from": ats, "slug": target,
                         "count": n, "action": "migrate",
                         "detail": f"{n} live jobs => workday_cxs"})
            if apply:
                c["ats_type"] = "workday_cxs"
                c["slug"] = target
                migrated += 1
        else:
            why = "0 jobs / probe skipped" if (n == 0 or n is None) else str(n)
            rows.append({"name": name, "from": ats, "slug": target,
                         "count": n, "action": "leave",
                         "detail": f"422/dead/empty ({why}) -- untouched"})

    wrote = False
    if apply and migrated:
        from scrape.cache_helpers import write_cache
        raw["companies"] = companies
        write_cache(json_path, raw)
        wrote = True

    return {"candidates": len(cands), "migrated": migrated, "wrote": wrote,
            "rows": rows, "applied": apply}


def _print_report(rep: dict, json_path: Path, apply: bool) -> None:
    if rep.get("error"):
        print(f"ERROR: {rep['error']}")
        return
    rows = rep["rows"]
    print(f"companies.json: {json_path}")
    print(f"Workday candidates found: {rep['candidates']}\n")
    if not rows:
        print("  (no 'direct' myworkdayjobs.com rows and no legacy 'workday' rows "
              "to migrate)")
    else:
        print(f"  {'NAME':30} {'FROM':8} {'JOBS':>5}  {'ACTION':8} DETAIL")
        print(f"  {'-'*30} {'-'*8} {'-'*5}  {'-'*8} {'-'*40}")
        for r in rows:
            cnt = "-" if r["count"] is None else str(r["count"])
            print(f"  {r['name'][:30]:30} {r['from']:8} {cnt:>5}  "
                  f"{r['action']:8} {r['detail']}")
    n_mig = sum(1 for r in rows if r["action"] == "migrate")
    n_leave = sum(1 for r in rows if r["action"] == "leave")
    n_skip = sum(1 for r in rows if r["action"] == "skip")
    print(f"\n  would migrate: {n_mig} | leave (dead/walled): {n_leave} | "
          f"skip (no slug): {n_skip}")
    if apply:
        if rep["wrote"]:
            print(f"\n[applied] relabeled {rep['migrated']} row(s) to workday_cxs "
                  f"and wrote {json_path.name}.")
        else:
            print("\n[applied] nothing to write (no row passed its live probe).")
    else:
        print("\n[dry-run] nothing written. Re-run with --apply to relabel the "
              "'migrate' rows above.")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Relabel parked/legacy Workday rows in companies.json to the "
                    "public workday_cxs reader (live-probe verified).")
    ap.add_argument("--json", default=None,
                    help="companies.json path (default: config.COMPANIES_JSON)")
    ap.add_argument("--apply", action="store_true",
                    help="Write the relabels (default: dry-run, report only)")
    ap.add_argument("--limit", type=int, default=None,
                    help="Only probe the first N candidates (gentle live probing)")
    ap.add_argument("--no-probe", action="store_true",
                    help="Skip the live probe (offline preview of candidates only; "
                         "nothing is ever migrated without a live >0 probe)")
    args = ap.parse_args(argv)

    if args.json:
        json_path = Path(args.json)
    else:
        from config import COMPANIES_JSON
        json_path = COMPANIES_JSON

    rep = migrate(json_path, apply=args.apply, limit=args.limit,
                  probe=not args.no_probe)
    _print_report(rep, json_path, args.apply)
    return 2 if rep.get("error") else 0


if __name__ == "__main__":
    raise SystemExit(main())
