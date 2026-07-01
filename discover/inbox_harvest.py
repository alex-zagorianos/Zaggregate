"""Inbox -> company registry harvester.

Grows the registry from employer names we've ALREADY seen hiring, instead of
asking an LLM to enumerate candidates (see enumerate_companies.py for that
path). Because every name here came from a real search result already
persisted to the inbox, there's no hallucination risk going in — the only new
problem this module solves is that an inbox row has just a display name, no
domain. It reuses the same resolve -> verify -> save backbone as
enumerate_companies.resolve_and_verify (career-URL discovery -> ATS
fingerprint -> live probe_count>0 gate); this module only adds a domain-GUESS
step in front of it, and the probe is the safety net that drops bad guesses.

Free, deterministic, no API key, and compounds every run: a name only drops
out once it's already in the registry or has been tried and failed to
resolve (nothing here writes a negative cache, so a bad guess this run may
still resolve on a later run if the company's site or ATS changes).

Examples:
  py -3.12 discover/inbox_harvest.py --dry-run
  py -3.12 discover/inbox_harvest.py --industry controls --min-count 2 --limit 25
"""
from __future__ import annotations

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

# Mirrors enumerate_companies.py's bootstrap so `py discover/inbox_harvest.py`
# works standalone too (this file sits one level deeper, hence parent.parent).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from coverage.entity import canonicalize_company
from discover.career_link import find_career_url
from discover.detect import detect_ats
from scrape.ats_detect import probe_count
from scrape.company_registry import CompanyEntry, get_registry, save_companies
from tracker.db import inbox_company_counts, inbox_company_display_names

# Placeholder/junk employer names that show up verbatim in scraped postings —
# never worth a network round-trip. Anything <= 1 char is junk too.
_JUNK_NAMES = {"unknown", "n/a", "na", "none", "-", "null", "undisclosed", "confidential"}


def _is_junk(name: str) -> bool:
    n = (name or "").strip()
    if len(n) <= 1:
        return True
    return n.lower() in _JUNK_NAMES


def _domain_guesses(name: str) -> list[str]:
    """Candidate domains for a bare company name, most-likely first.

    Built on coverage.entity.canonicalize_company, which already strips legal
    suffixes/punctuation and lowercases (and resolves known aliases) — so
    "Acme Robotics, Inc." and "ACME ROBOTICS" collapse to the same guesses.

    We deliberately do NOT shorten a multi-word name to its bare first word
    (e.g. "Apex Controls" -> "apex.com"): the probe gate only verifies a board
    is LIVE, not that it belongs to THIS employer, so a bare common-word domain
    owned by an unrelated real company with open jobs would be saved under the
    wrong name. The full-token guesses ("apexcontrols.*") are specific enough to
    be safe; anything they miss is left for the LLM-enumerate path.
    """
    canon = canonicalize_company(name)
    words = canon.split()
    if not words:
        return []
    token = "".join(words)   # "acme robotics" -> "acmerobotics"
    guesses = [f"{token}.com", f"{token}.io", f"{token}.co"]
    seen: set[str] = set()
    out: list[str] = []
    for g in guesses:
        if g not in seen:
            seen.add(g)
            out.append(g)
    return out


@dataclass
class HarvestResult:
    candidates: int
    already_in_registry: int
    resolved: int
    verified: int
    added: int
    entries: list[CompanyEntry] = field(default_factory=list)


def harvest_inbox_companies(industry: str | None = None, *, min_count: int = 1,
                            limit: int | None = None, max_workers: int = 8,
                            dry_run: bool = False, companies_json=None) -> HarvestResult:
    """Resolve inbox employer names we've already seen hiring into verified
    registry entries.

    1. Pull distinct inbox company names + counts (tracker.db.inbox_company_counts),
       keep count >= min_count, drop obvious junk names.
    2. Drop names already present in the merged registry (scrape.company_registry
       .get_registry), matched via coverage.entity.canonicalize_company.
    3. Cap to `limit` (highest-count first).
    4. Threaded resolve: guess candidate domains -> find_career_url -> detect_ats
       -> probe_count > 0. First hit per name wins; anything that never
       resolves/verifies is simply dropped (mirrors enumerate_companies
       .resolve_and_verify).
    5. Build CompanyEntry(name, ats_type, slug, industries=[industry] if
       industry else ["harvested"]) for each verified name; unless dry_run,
       save_companies() them.
    """
    json_path = Path(companies_json) if companies_json else None

    raw_counts = inbox_company_counts()
    eligible = [(name, count) for name, count in raw_counts.items()
                if count >= min_count and not _is_junk(name)]
    candidates = len(eligible)

    registry_keys = {canonicalize_company(e.name) for e in get_registry(user_json=json_path)}
    fresh = [(name, count) for name, count in eligible
             if canonicalize_company(name) not in registry_keys]
    already_in_registry = candidates - len(fresh)

    fresh.sort(key=lambda t: t[1], reverse=True)
    if limit is not None:
        fresh = fresh[:limit]

    tags = [industry] if industry else ["harvested"]

    # inbox_company_counts() keys are lowercased; recover the real display casing
    # so the saved CompanyEntry.name isn't permanently lowercased (which would also
    # block a later correctly-cased add via save_companies' name-based dedup).
    try:
        display = inbox_company_display_names()
    except Exception:
        display = {}

    def _one(name: str):
        """name -> (resolved: bool, entry_or_None). `resolved` is True as soon
        as ANY domain guess reaches a detected ATS board, even if that guess
        turns out to have zero live jobs and a later guess is tried."""
        resolved_flag = False
        for domain in _domain_guesses(name):
            try:
                url = find_career_url(domain)
            except Exception:
                url = None
            if not url:
                continue
            try:
                det = detect_ats(url)
            except Exception:
                det = None
            if not det:
                continue
            resolved_flag = True
            ats_type, slug = det
            entry = CompanyEntry(display.get(name, name), ats_type, slug, list(tags))
            try:
                n = probe_count(entry)
            except Exception:
                n = None
            if n is not None and n > 0:
                return (resolved_flag, entry)
        return (resolved_flag, None)

    results: dict[str, tuple] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = {ex.submit(_one, name): name for name, _ in fresh}
        for fut in as_completed(futs):
            name = futs[fut]
            results[name] = fut.result()

    resolved = sum(1 for r, _ in results.values() if r)
    # Rebuild in `fresh` (count-desc) order for deterministic output, rather
    # than as_completed's arbitrary thread-scheduling order.
    entries = [entry for name, _ in fresh if (entry := results[name][1]) is not None]
    verified = len(entries)

    added = len(entries) if dry_run else save_companies(entries, json_path)

    return HarvestResult(candidates=candidates, already_in_registry=already_in_registry,
                         resolved=resolved, verified=verified, added=added, entries=entries)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Harvest employers already seen hiring (inbox) into the verified company registry.")
    ap.add_argument("--industry", default=None,
                    help="Industry tag stamped on adds (default: 'harvested')")
    ap.add_argument("--min-count", type=int, default=1,
                    help="Minimum inbox postings before a company is considered (default: 1)")
    ap.add_argument("--limit", type=int, default=None,
                    help="Max companies to attempt this run (highest inbox count first)")
    ap.add_argument("--dry-run", action="store_true", help="Resolve + verify but do NOT save")
    ap.add_argument("--json", default=None, help="companies.json path override (default: COMPANIES_JSON)")
    args = ap.parse_args(argv)

    result = harvest_inbox_companies(args.industry, min_count=args.min_count, limit=args.limit,
                                     dry_run=args.dry_run, companies_json=args.json)

    print(f"Inbox employers considered: {result.candidates} "
          f"(already in registry: {result.already_in_registry})")
    print(f"Resolved to an ATS board: {result.resolved} | verified (live jobs): {result.verified}")
    for e in result.entries:
        print(f"  + {e.name[:34]:34} | {e.ats_type:15} | {e.slug[:26]:26}")

    if args.dry_run:
        print(f"\n[dry-run] {result.added} compan(ies) would be added; nothing written.")
    else:
        print(f"\nAdded {result.added} new compan(ies) to companies.json.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
