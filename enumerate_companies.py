"""Grow the company registry by enumerating LOCAL employers, then verifying them.

Pipeline:
  1. ENUMERATE  {name, domain} candidates for a metro + industries — via the
     Anthropic API if a key is present, else a clipboard bridge (paste a prompt
     into claude.ai, paste the JSON reply back with --in).  [discover.enumerate]
  2. RESOLVE    each domain -> careers URL -> ATS board.   [discover.funnel/detect]
  3. VERIFY     probe the board; keep only companies with live jobs (>0). This is
     the gate that makes LLM enumeration safe — hallucinated/dead companies are
     dropped here.                                          [scrape.ats_detect]
  4. SAVE       append verified boards to companies.json (user-wins dedup), tagged
     with the industries + a metro tag.            [scrape.company_registry]

Examples:
  py enumerate_companies.py --metro Cincinnati --industries controls,software --dry-run
  py enumerate_companies.py --print-prompt > prompt.txt     # bridge: paste into claude.ai
  py enumerate_companies.py --in reply.json                 # bridge: feed the pasted reply
  py enumerate_companies.py                                  # API auto (needs a key)
"""
from __future__ import annotations

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from discover import enumerate as enum
from discover import career_link
from discover.detect import detect_ats
from scrape.ats_detect import probe_count
from scrape.company_registry import CompanyEntry, get_registry, save_companies

DEFAULT_INDUSTRIES = ["controls", "software", "applied-ai", "mechanical",
                      "robotics", "embedded"]
DEFAULT_METRO_TAG = "cincinnati"


def resolve_domain(domain: str):
    """domain -> (ats_type, slug) or None (no resolvable ATS board behind it)."""
    url = career_link.find_career_url(domain)
    if not url:
        return None
    return detect_ats(url)


def resolve_and_verify(candidates, industries, *, metro_tag=DEFAULT_METRO_TAG,
                       resolve=resolve_domain, probe=probe_count,
                       existing_names=None, max_workers=12):
    """Resolve + probe-verify candidate {name, domain} dicts.

    Returns (verified, dropped):
      verified = [(CompanyEntry, open_job_count)] sorted best-first
      dropped  = [(candidate, reason)]
    `resolve` and `probe` are injectable for testing.
    """
    existing = {(n or "").strip().lower() for n in (existing_names or [])}
    tags = list(dict.fromkeys(list(industries) + [metro_tag]))  # de-dup, keep order

    def _one(cand):
        name = (cand.get("name") or "").strip()
        if not name:
            return (cand, "no name", None)
        if name.lower() in existing:
            return (cand, "already known", None)
        try:
            det = resolve(cand.get("domain", ""))
        except Exception as e:
            return (cand, f"resolve error: {type(e).__name__}", None)
        if not det:
            return (cand, "no ATS board detected", None)
        ats_type, slug = det
        entry = CompanyEntry(name, ats_type, slug, list(tags))
        try:
            n = probe(entry)
        except Exception as e:
            return (cand, f"probe error: {type(e).__name__}", None)
        if n is None:
            return (cand, f"unverifiable board ({ats_type})", None)
        if n <= 0:
            return (cand, "no live jobs", None)
        return (cand, "ok", (entry, n))

    verified, dropped = [], []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = [ex.submit(_one, c) for c in candidates]
        for fut in as_completed(futs):
            cand, reason, payload = fut.result()
            if payload is not None:
                verified.append(payload)
            else:
                dropped.append((cand, reason))
    verified.sort(key=lambda t: t[1], reverse=True)
    return verified, dropped


def _existing_names(json_path):
    try:
        return [e.name for e in get_registry(user_json=json_path)]
    except Exception:
        return []


def _resolve_metro(arg_metro):
    if arg_metro:
        return arg_metro
    try:
        import workspace
        loc = (workspace.load_config().get("location") or "").strip()
        if loc:
            return loc
    except Exception:
        pass
    from config import DEFAULT_LOCATION
    return DEFAULT_LOCATION


def _resolve_industry(arg_industry):
    """Single field/industry for enumeration-angle selection (mirrors
    _resolve_metro): CLI > active-project config `industry` > DEFAULT_INDUSTRY.
    Empty/eng-like -> DEFAULT_ANGLES (Alex's controls flow unchanged)."""
    if arg_industry:
        return arg_industry
    try:
        import workspace
        ind = (workspace.load_config().get("industry") or "").strip()
        if ind:
            return ind
    except Exception:
        pass
    import config
    return getattr(config, "DEFAULT_INDUSTRY", "")


def _remote_ok():
    """True when the active project's hard preferences allow remote (plan P5)."""
    try:
        import preferences
        return bool(preferences.load().get("hard", {}).get("remote_ok", True))
    except Exception:
        return False


# Prompt "metro" for the nationwide/remote-first enumeration pass.
NATIONAL_METRO = "the United States (nationwide, remote-friendly employers)"


def main(argv=None):
    ap = argparse.ArgumentParser(description="Enumerate + verify local companies into companies.json")
    ap.add_argument("--metro", default=None, help="Metro area (default: active project location)")
    ap.add_argument("--industries", default=",".join(DEFAULT_INDUSTRIES),
                    help="Comma-separated industry tags (for the prompt's role list)")
    ap.add_argument("--industry", default=None,
                    help="Single field for enumeration-angle selection "
                         "(default: active project industry / DEFAULT_INDUSTRY)")
    ap.add_argument("--metro-tag", default=DEFAULT_METRO_TAG, help="Extra tag stamped on adds")
    ap.add_argument("--limit", type=int, default=40, help="Max companies per enumeration angle")
    ap.add_argument("--json", default=None, help="companies.json path (default: COMPANIES_JSON)")
    ap.add_argument("--bridge", action="store_true", help="Force the clipboard bridge (no API call)")
    ap.add_argument("--print-prompt", action="store_true",
                    help="Print the enumeration prompt for claude.ai and exit (bridge)")
    ap.add_argument("--in", dest="infile", default=None,
                    help="Read a pasted JSON reply (bridge) instead of calling the API")
    grp = ap.add_mutually_exclusive_group()
    grp.add_argument("--national", dest="national", action="store_true", default=None,
                     help="Also enumerate nationwide/remote-first employers "
                          "(default: on when the project's preferences allow remote)")
    grp.add_argument("--no-national", dest="national", action="store_false",
                     help="Metro-only, even if remote is allowed")
    ap.add_argument("--dry-run", action="store_true", help="Resolve + verify but do NOT save")
    args = ap.parse_args(argv)

    metro = _resolve_metro(args.metro)
    industries = [s.strip() for s in args.industries.split(",") if s.strip()]
    industry = _resolve_industry(args.industry)
    angles = enum.angles_for_industry(industry)
    json_path = Path(args.json) if args.json else None
    names = _existing_names(json_path)

    # ── Bridge: print the prompt and exit ──────────────────────────────────────
    if args.print_prompt or (args.bridge and not args.infile):
        prompt = enum.build_enumeration_prompt(metro, industries, exclude_names=names,
                                               angle="Include a mix of company sizes "
                                               "and types.", limit=max(args.limit, 60))
        print(prompt)
        print("\n# Paste the above into claude.ai, then save its JSON reply to a file and run:")
        print("#   py enumerate_companies.py --in reply.json"
              + (f" --metro {metro}" if args.metro else ""))
        return 0

    run_national = args.national if args.national is not None else _remote_ok()

    # ── Build the pass list: metro always; a nationwide/remote-first pass too when
    #    remote is allowed. Each pass = (candidates, industries, metro_tag). ───────
    passes = []  # (candidates, pass_industries, metro_tag)
    if args.infile:
        text = Path(args.infile).read_text(encoding="utf-8")
        metro_cands = enum.dedupe_candidates(enum.parse_enumeration_response(text))
        print(f"Parsed {len(metro_cands)} candidate(s) from {args.infile}.")
        passes.append((metro_cands, industries, args.metro_tag))
    else:
        try:
            metro_cands = enum.dedupe_candidates(
                enum.enumerate_via_api(metro, industries, exclude_names=names,
                                       angles=angles, limit=args.limit))
            print(f"Enumerated {len(metro_cands)} candidate(s) via API for '{metro}'"
                  + (f" [{industry}]" if industry else "") + ".")
            passes.append((metro_cands, industries, args.metro_tag))
            if run_national:
                seen = {enum.normalize_domain(c["domain"]) for c in metro_cands}
                natl_angles = enum.angles_for_industry(industry, scope="national")
                natl_cands = enum.dedupe_candidates(
                    enum.enumerate_via_api(NATIONAL_METRO, industries, exclude_names=names,
                                           exclude_domains=seen, angles=natl_angles,
                                           limit=args.limit),
                    exclude_domains=seen)
                print(f"Enumerated {len(natl_cands)} nationwide/remote candidate(s).")
                # national adds carry national+remote tags (metro tag is dropped);
                # their jobs surface under the inbox's remote/all views (geo/filter).
                passes.append((natl_cands, industries + ["national", "remote"], "remote"))
        except RuntimeError as e:
            print(f"{e}\nRe-run with --print-prompt (bridge) or set an API key.")
            return 2

    total_cands = sum(len(c) for c, _, _ in passes)
    if not total_cands:
        print("No candidates to verify.")
        return 0

    # ── Resolve + verify each pass (later passes exclude earlier verified names) ──
    print(f"Resolving + probing {total_cands} candidate(s)…")
    verified, dropped = [], []
    known = list(names)
    for cands, pass_inds, metro_tag in passes:
        if not cands:
            continue
        v, d = resolve_and_verify(cands, pass_inds, metro_tag=metro_tag,
                                  existing_names=known)
        verified.extend(v)
        dropped.extend(d)
        known.extend(e.name for e, _ in v)
    print(f"\nVERIFIED (live boards): {len(verified)} | dropped: {len(dropped)}")
    for e, n in verified:
        print(f"  + {e.name[:34]:34} | {e.ats_type:15} | {e.slug[:26]:26} | {n} jobs")
    # Show a few drop reasons so selector/enumeration quality is visible.
    from collections import Counter
    reasons = Counter(r for _, r in dropped)
    if reasons:
        print("  dropped reasons:", dict(reasons))

    if args.dry_run:
        print("\n[dry-run] nothing written.")
        return 0
    added = save_companies([e for e, _ in verified], json_path)
    print(f"\nAdded {added} new compan(ies) to companies.json.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
