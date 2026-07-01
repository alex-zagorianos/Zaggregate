"""Bulk-seed companies.json from an open ATS-slug dataset (plan P1).

Unlike enumerate_companies.py (LLM proposes {name, domain} -> resolve -> verify),
this skips the resolver entirely: open datasets already list (ats_type, slug), so
each is fed straight through the same live probe-verify gate. Deterministic, $0,
no hallucination.

Get a dataset (one-time, offline):
  - jobhive (MIT, ~86k boards / 47 ATSes) or OpenJobs (MIT, has an industry column).
  - If it ships as parquet, convert to CSV once (any tool), e.g.:
        python -c "import pandas as pd; pd.read_parquet('x.parquet').to_csv('x.csv', index=False)"
    (pandas is NOT a project dependency — do this in a throwaway env.)

Examples:
  py seed_companies.py --dataset boards.csv --industry health_informatics --dry-run
  py seed_companies.py --dataset boards.csv --industry controls_engineering --ats greenhouse,lever,ashby
  py seed_companies.py --dataset boards.ndjson --limit 500
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config
from discover import dataset_seed


def _resolve_industry(arg_industry: str | None) -> str:
    """CLI > active-project config `industry` > config.DEFAULT_INDUSTRY."""
    if arg_industry:
        return arg_industry
    try:
        import workspace
        cfg = workspace.load_config()
        ind = (cfg.get("industry") or "").strip()
        if ind:
            return ind
    except Exception:
        pass
    return getattr(config, "DEFAULT_INDUSTRY", "")


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Bulk-seed companies.json from an open ATS-slug dataset (probe-verified).")
    ap.add_argument("--dataset", required=True, help="Path to a CSV/TSV/NDJSON/JSON ATS-slug dataset")
    ap.add_argument("--industry", default=None,
                    help="Industry tag stamped on adds (default: active project / DEFAULT_INDUSTRY)")
    ap.add_argument("--ats", default=None,
                    help="Comma-separated ATS filter (e.g. greenhouse,lever,ashby)")
    ap.add_argument("--limit", type=int, default=None, help="Max dataset rows to read")
    ap.add_argument("--max-workers", type=int, default=12, help="Probe concurrency")
    ap.add_argument("--json", default=None, help="companies.json path (default: COMPANIES_JSON)")
    ap.add_argument("--col-ats", default=None, help="Override the ATS column name")
    ap.add_argument("--col-slug", default=None, help="Override the slug column name")
    ap.add_argument("--dry-run", action="store_true", help="Probe-verify but do NOT save")
    args = ap.parse_args(argv)

    ds = Path(args.dataset)
    if not ds.exists():
        print(f"Dataset not found: {ds}")
        return 2

    industry = _resolve_industry(args.industry)
    ats_filter = [s.strip() for s in args.ats.split(",")] if args.ats else None
    column_map = {}
    if args.col_ats:
        column_map["ats"] = args.col_ats
    if args.col_slug:
        column_map["slug"] = args.col_slug
    json_path = Path(args.json) if args.json else None

    print(f"Loading {ds.name} (industry='{industry or 'discovered'}'"
          + (f", ats={ats_filter}" if ats_filter else "") + ")…")
    result = dataset_seed.seed_from_dataset(
        ds, industry, max_workers=args.max_workers, limit=args.limit,
        ats_filter=ats_filter, column_map=column_map or None,
        companies_json_path=json_path, dry_run=args.dry_run)

    print(f"  loaded {result['loaded']} board(s) | "
          f"{result['skipped_known']} already known | "
          f"probed {result['candidates']}")
    print(f"VERIFIED (live boards): {len(result['verified'])} | "
          f"dropped: {len(result['dropped'])}")
    for e, n in result["verified"][:40]:
        print(f"  + {e.name[:32]:32} | {e.ats_type:15} | {e.slug[:24]:24} | {n} jobs")
    if len(result["verified"]) > 40:
        print(f"  … and {len(result['verified']) - 40} more")
    reasons = Counter(r for _, _, r in result["dropped"])
    if reasons:
        print("  dropped reasons:", dict(reasons))

    if args.dry_run:
        print("\n[dry-run] nothing written.")
        return 0
    print(f"\nAdded {result['added']} new compan(ies) to companies.json.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
