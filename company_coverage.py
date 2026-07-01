"""Estimate how complete the company registry is, by capture-recapture against a
second INDEPENDENT company list.

  py company_coverage.py --against harvest_names.txt
  py company_coverage.py --against pdl_domains.txt --key domain

list A = the current registry (companies.json). list B = the --against file, one
company per line (a name, or a domain/URL with --key domain). The second list
must be built INDEPENDENTLY of the registry for the estimate to be valid — e.g.
a Common-Crawl ATS harvest, or a firmographic export (PDL / AtoZ / library DB).
Do NOT use the LLM enumerator's output (it's seeded from the registry's gaps, so
it's correlated and inflates the estimate). See coverage/registry_coverage.py.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from coverage.registry_coverage import (domain_identity, estimate_coverage,
                                        name_identity)
from scrape.company_registry import get_registry


def _read_list(path: Path) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [ln.strip() for ln in lines if ln.strip() and not ln.lstrip().startswith("#")]


def main(argv=None):
    ap = argparse.ArgumentParser(description="Capture-recapture coverage of companies.json")
    ap.add_argument("--against", required=True,
                    help="File with the second (independent) company list, one per line")
    ap.add_argument("--key", choices=["name", "domain"], default="name",
                    help="Identity space both lists share (default: name)")
    ap.add_argument("--industry", default=None,
                    help="Restrict the registry to one industry tag before measuring")
    ap.add_argument("--json", default=None, help="companies.json path (default: COMPANIES_JSON)")
    ap.add_argument("--record", action="store_true",
                    help="Append this estimate to the industry's coverage history jsonl")
    ap.add_argument("--loop-signal", action="store_true",
                    help="Print the loop-until-dry verdict (rising/plateau/dry) from history")
    args = ap.parse_args(argv)

    key = domain_identity if args.key == "domain" else name_identity
    registry = get_registry(industry=args.industry,
                            user_json=Path(args.json) if args.json else None)
    other = _read_list(Path(args.against))

    est = estimate_coverage(registry, other, key=key)
    print(est.summary(label_a="registry (companies.json)", label_b=Path(args.against).name))

    if args.record:
        from coverage.registry_history import record
        path = record(est, args.industry or "", extra={"list_b": Path(args.against).name})
        print(f"\nRecorded to {path}")
    if args.loop_signal:
        from coverage.registry_coverage import loop_signal
        from coverage.registry_history import load_history
        sig = loop_signal(load_history(args.industry or ""))
        print(f"Loop signal: {sig.upper()}  "
              + {"rising": "(keep acquiring companies)",
                 "plateau": "(coverage high + growth <2% — good enough)",
                 "dry": "(last round added nothing new — stop)"}.get(sig, ""))

    if not est.defined:
        print("\nTip: ensure both lists use the same identity space (--key) and that the "
              "second list is independent of the registry.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
