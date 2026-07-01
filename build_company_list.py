"""ONE onboarding command: build a target-company list for ANY field + location.

A brand-new user (any profession, not just Alex's controls/software flow) should
not have to know that a healthy `companies.json` comes out of stitching together
four separate scripts. This module orchestrates the EXISTING pieces:

  1. INBOX HARVEST   companies already seen in the user's job inbox that aren't
                      in the registry yet.                 [discover.inbox_harvest]
  2. LLM ENUMERATE    metro (+ optional nationwide/remote) employers for the
                      user's field, resolved + probe-verified.  [enumerate_companies
                      / discover.enumerate]
  3. DATASET SEED     (optional) bulk-import an open ATS-slug dataset.
                                                              [discover.dataset_seed]
  4. CLASSIFY         (optional) relevance gate applied to the dataset seed.
                                                                 [discover.classify]
  5. REPORT           registry stats + loop-until-dry signal for the field.
                                        [scrape.company_registry / coverage.*]

Every stage is best-effort: a failure or missing piece is logged and skipped, it
never aborts the whole run. Field + location are DERIVED from the active (or
named) project's config when not passed explicitly -- there is no hardcoded
"cincinnati"/engineering default; if neither can be resolved, this raises a clear
error telling the user how to fix it.

Examples:
  py build_company_list.py                                  # active project, API auto
  py build_company_list.py --project health-informatics --national
  py build_company_list.py --print-prompt > prompt.txt       # no API key: bridge
  py build_company_list.py --in reply.json                   # feed the pasted reply
  py build_company_list.py --industry nursing --metro "Columbus, OH" --dry-run
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import workspace
from coverage.registry_coverage import loop_signal
from coverage.registry_history import load_history
from discover.classify import make_classifier
from discover.dataset_seed import seed_from_dataset
from discover.enumerate import (angles_for_industry, build_enumeration_prompt,
                                dedupe_candidates, enumerate_via_api,
                                normalize_domain, parse_enumeration_response)
from enumerate_companies import NATIONAL_METRO, resolve_and_verify
from scrape.company_registry import get_registry, registry_stats, save_companies


# ── small helpers ───────────────────────────────────────────────────────────────
def _count(value) -> int:
    """len() when possible, else pass an int/None through as a count."""
    try:
        return len(value)
    except TypeError:
        return int(value) if value else 0


def _project_config(project: str | None) -> dict:
    try:
        return workspace.load_config(project) or {}
    except Exception:
        return {}


def _resolve_field(explicit: str | None, project: str | None, key: str) -> str:
    """CLI/arg value > the (active or named) project's config[key]. NO further
    fallback -- callers decide what an unresolved field means."""
    if explicit and str(explicit).strip():
        return str(explicit).strip()
    return str(_project_config(project).get(key) or "").strip()


def _existing_names() -> list[str]:
    try:
        return [e.name for e in get_registry()]
    except Exception:
        return []


def _metro_tag(metro: str) -> str:
    """A generic slug tag for saved entries -- derived from the metro string
    itself (workspace.slugify), never a hardcoded metro name."""
    try:
        tag = workspace.slugify(metro or "")
        if tag:
            return tag
    except Exception:
        pass
    return re.sub(r"[^a-z0-9]+", "-", (metro or "").strip().lower()).strip("-") or "national"


def _detect_api_key(explicit: str | None = None) -> str | None:
    """Whether an Anthropic key is available for the auto enumerate route. An
    explicit caller-supplied key always wins; else defer to ranker.api_key()
    (env var or secrets/anthropic_key -- the same detector every other API/bridge
    duality in this app uses)."""
    if explicit:
        return explicit
    try:
        import ranker
        return ranker.api_key()
    except Exception:
        return None


# ── stage 1: inbox harvest ──────────────────────────────────────────────────────
def _harvest_inbox(industry: str, dry_run: bool, log=print) -> dict:
    print = log  # route this stage's narration through the caller's sink
    try:
        from discover.inbox_harvest import harvest_inbox_companies
    except ImportError:
        print("[inbox] discover/inbox_harvest.py is not available yet -- skipping "
              "this stage.")
        return {"skipped": "module not available"}
    try:
        result = harvest_inbox_companies(industry=industry or None, dry_run=dry_run)
    except Exception as e:
        print(f"[inbox] harvest failed ({type(e).__name__}: {e}) -- skipping.")
        return {"error": str(e)}
    out = {
        "candidates": _count(result.candidates),
        "already_in_registry": _count(result.already_in_registry),
        "resolved": _count(result.resolved),
        "verified": _count(result.verified),
        "added": _count(result.added),
    }
    print(f"[inbox] {out['candidates']} candidate(s) from your inbox, "
          f"{out['already_in_registry']} already known, {out['verified']} verified "
          f"live, {out['added']} added.")
    return out


# ── stage 2: LLM enumerate (API auto / clipboard bridge) ───────────────────────
def _enumerate_stage(*, metro: str, industry: str, national: bool, print_prompt: bool,
                     in_file: str | None, dry_run: bool, key: str | None, log=print) -> dict:
    print = log  # route this stage's narration through the caller's sink
    industries = [industry] if industry else []
    existing = _existing_names()
    tag = _metro_tag(metro)

    # ── bridge: feed a pasted reply ─────────────────────────────────────────────
    if in_file:
        try:
            text = Path(in_file).read_text(encoding="utf-8")
        except OSError as e:
            print(f"[enumerate] could not read {in_file}: {e}")
            return {"mode": "bridge-in", "error": str(e)}
        cands = dedupe_candidates(parse_enumeration_response(text))
        print(f"[enumerate] Parsed {len(cands)} candidate(s) from {in_file}.")
        if not cands:
            return {"mode": "bridge-in", "candidates": 0, "verified": 0, "added": 0}
        verified, dropped = resolve_and_verify(cands, industries, metro_tag=tag,
                                               existing_names=existing)
        added = 0
        if not dry_run and verified:
            added = save_companies([e for e, _ in verified])
        print(f"[enumerate] verified {len(verified)}, dropped {len(dropped)}, "
              f"added {added}.")
        return {"mode": "bridge-in", "candidates": len(cands), "verified": len(verified),
                "dropped": len(dropped), "added": added}

    # ── bridge: print the prompt and stop this stage ────────────────────────────
    if print_prompt or not key:
        if not key and not print_prompt:
            print("[enumerate] No Anthropic API key configured -- printing the "
                  "clipboard-bridge prompt instead of calling the API.")
        prompt = build_enumeration_prompt(
            metro, industries, exclude_names=existing,
            angle="Include a mix of company sizes and types.", limit=60)
        print(prompt)
        print("\n# Paste the above into claude.ai, save its JSON reply to a file "
              "(e.g. reply.json), then re-run with:")
        print(f"#   py build_company_list.py --industry \"{industry}\" "
              f"--metro \"{metro}\" --in reply.json")
        return {"mode": "bridge-prompt", "printed": True}

    # ── API auto mode ────────────────────────────────────────────────────────────
    angles = angles_for_industry(industry)
    try:
        cands = dedupe_candidates(enumerate_via_api(
            metro, industries, exclude_names=existing, angles=angles, limit=40))
    except RuntimeError as e:
        print(f"[enumerate] {e}")
        return {"mode": "api", "error": str(e)}
    print(f"[enumerate] Enumerated {len(cands)} candidate(s) via API for '{metro}'.")

    passes = [(cands, industries, tag)]
    if national:
        seen = {normalize_domain(c["domain"]) for c in cands}
        natl_angles = angles_for_industry(industry, scope="national")
        natl_cands = dedupe_candidates(
            enumerate_via_api(NATIONAL_METRO, industries, exclude_names=existing,
                              exclude_domains=seen, angles=natl_angles, limit=40),
            exclude_domains=seen)
        print(f"[enumerate] Enumerated {len(natl_cands)} nationwide/remote candidate(s).")
        passes.append((natl_cands, industries + ["national", "remote"], "remote"))

    verified_all, dropped_all = [], []
    known = list(existing)
    for cands_p, inds_p, tag_p in passes:
        if not cands_p:
            continue
        v, d = resolve_and_verify(cands_p, inds_p, metro_tag=tag_p, existing_names=known)
        verified_all.extend(v)
        dropped_all.extend(d)
        known.extend(e.name for e, _ in v)

    added = 0
    if not dry_run and verified_all:
        added = save_companies([e for e, _ in verified_all])
    print(f"[enumerate] verified {len(verified_all)}, dropped {len(dropped_all)}, "
          f"added {added}.")
    return {"mode": "api", "candidates": sum(len(c) for c, _, _ in passes),
            "verified": len(verified_all), "dropped": len(dropped_all), "added": added}


# ── stage 3/4: dataset seed + relevance classify ────────────────────────────────
def _dataset_stage(dataset: str, industry: str, classify: bool, dry_run: bool, log=print) -> dict:
    print = log  # route this stage's narration through the caller's sink
    classifier = make_classifier(industry) if classify else None
    result = seed_from_dataset(dataset, industry=industry or "", classify=classifier,
                               dry_run=dry_run)
    out = {
        "loaded": result.get("loaded", 0),
        "candidates": result.get("candidates", 0),
        "skipped_known": result.get("skipped_known", 0),
        "verified": _count(result.get("verified", [])),
        "dropped": _count(result.get("dropped", [])),
        "added": result.get("added", 0),
        "classified": bool(classifier),
    }
    print(f"[dataset] loaded {out['loaded']}, verified {out['verified']}, "
          f"added {out['added']} (classify={'on' if classifier else 'off'}).")
    return out


# ── orchestrator ─────────────────────────────────────────────────────────────────
def build_company_list(*, project: str | None = None, metro: str | None = None,
                       industry: str | None = None, national: bool = False,
                       dataset: str | None = None, use_inbox: bool = True,
                       print_prompt: bool = False, in_file: str | None = None,
                       classify: bool = False, dry_run: bool = False,
                       api_key: str | None = None, log=print) -> dict:
    """Build (or grow) a target-company list for the active/named project's field
    + location. Orchestrates the existing inbox-harvest / LLM-enumerate /
    dataset-seed / classify / coverage-report pipeline; never invents a field or
    location default. Returns a summary dict:

        {"industry", "metro", "national", "stages": {...},
         "registry_stats", "loop_signal"}

    Raises ValueError when neither `industry` nor `metro` can be resolved from
    the arguments or the active project's config. `log` (default: print) is a
    line sink; a GUI passes a thread-safe callback so no global sys.stdout
    redirect is needed.
    """
    print = log  # route all narration below through the caller's sink
    resolved_industry = _resolve_field(industry, project, "industry")
    resolved_metro = _resolve_field(metro, project, "location")
    if not resolved_industry and not resolved_metro:
        raise ValueError(
            "No field (--industry) or location (--metro) to build a company list "
            "for, and neither could be derived from an active project. Pass "
            "--industry and/or --metro explicitly, or select/create a project "
            "first (gui.py's project switcher, or workspace.create_project(...))."
        )

    summary: dict = {
        "industry": resolved_industry,
        "metro": resolved_metro,
        "national": bool(national),
        "stages": {},
    }
    prompt_metro = resolved_metro or "your area"

    # 1 ── inbox harvest ─────────────────────────────────────────────────────────
    if use_inbox:
        print("== Inbox harvest ==")
        summary["stages"]["inbox"] = _harvest_inbox(resolved_industry, dry_run, log=log)
    else:
        print("== Inbox harvest (skipped, --no-inbox) ==")
        summary["stages"]["inbox"] = None

    # 2 ── LLM enumerate ─────────────────────────────────────────────────────────
    print("== LLM enumerate ==")
    key = _detect_api_key(api_key)
    try:
        summary["stages"]["enumerate"] = _enumerate_stage(
            metro=prompt_metro, industry=resolved_industry, national=national,
            print_prompt=print_prompt, in_file=in_file, dry_run=dry_run, key=key, log=log)
    except Exception as e:
        print(f"[enumerate] unexpected failure ({type(e).__name__}: {e}) -- skipping.")
        summary["stages"]["enumerate"] = {"error": str(e)}

    # 3/4 ── dataset seed + classify ─────────────────────────────────────────────
    if dataset:
        print("== Dataset seed ==")
        try:
            summary["stages"]["dataset"] = _dataset_stage(dataset, resolved_industry,
                                                           classify, dry_run, log=log)
        except Exception as e:
            print(f"[dataset] unexpected failure ({type(e).__name__}: {e}) -- skipping.")
            summary["stages"]["dataset"] = {"error": str(e)}
        summary["stages"]["classify"] = {"applied": bool(classify)}
    else:
        summary["stages"]["dataset"] = None
        if classify:
            print("[classify] --classify has no effect without --dataset (the "
                  "relevance gate is wired into the dataset-seed step) -- skipping.")
            summary["stages"]["classify"] = {"skipped": "no dataset given"}
        else:
            summary["stages"]["classify"] = None

    # 5 ── report ────────────────────────────────────────────────────────────────
    print("== Registry report ==")
    try:
        stats = registry_stats()
    except Exception as e:
        print(f"[report] registry_stats failed ({type(e).__name__}: {e}).")
        stats = {}
    try:
        signal = loop_signal(load_history(resolved_industry or ""))
    except Exception as e:
        print(f"[report] loop_signal failed ({type(e).__name__}: {e}).")
        signal = "rising"
    summary["registry_stats"] = stats
    summary["loop_signal"] = signal
    print(f"[report] registry now has {sum(stats.values())} total compan(ies) "
          f"across {len(stats)} tag(s); loop signal: {signal.upper()}.")
    return summary


# ── CLI ───────────────────────────────────────────────────────────────────────────
def _print_narrative(summary: dict) -> None:
    print("\n" + "=" * 64)
    print(f"Target-company list -- {summary['industry'] or '(any field)'} @ "
          f"{summary['metro'] or '(no location set)'}")
    print("=" * 64)
    for stage, data in summary["stages"].items():
        if data is None:
            print(f"  {stage:10}: skipped")
        elif "error" in data:
            print(f"  {stage:10}: FAILED -- {data['error']}")
        elif "skipped" in data:
            print(f"  {stage:10}: skipped -- {data['skipped']}")
        else:
            print(f"  {stage:10}: {data}")
    stats = summary.get("registry_stats") or {}
    print(f"\nRegistry: {sum(stats.values())} total compan(ies) across "
          f"{len(stats)} tag(s).")
    print(f"Loop signal: {(summary.get('loop_signal') or '?').upper()}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Build a target-company list for your field + location, in one command.")
    ap.add_argument("--project", default=None,
                    help="Project slug to read field/location from (default: active project)")
    ap.add_argument("--metro", default=None,
                    help="Metro/location to enumerate (default: project's location)")
    ap.add_argument("--industry", default=None,
                    help="Field/industry to enumerate for (default: project's industry)")
    ap.add_argument("--national", action="store_true",
                    help="Also enumerate nationwide/remote-first employers (API mode only)")
    ap.add_argument("--dataset", default=None,
                    help="Path to an open ATS-slug dataset (CSV/JSON) to bulk-seed from")
    ap.add_argument("--no-inbox", dest="use_inbox", action="store_false",
                    help="Skip harvesting companies already seen in your job inbox")
    ap.add_argument("--print-prompt", action="store_true",
                    help="Force the clipboard-bridge prompt even if an API key is configured")
    ap.add_argument("--in", dest="in_file", default=None,
                    help="Feed a saved claude.ai JSON reply (bridge mode) instead of calling the API")
    ap.add_argument("--classify", action="store_true",
                    help="Apply the relevance gate to dataset-seeded companies")
    ap.add_argument("--dry-run", action="store_true",
                    help="Resolve + verify but never write companies.json")
    ap.add_argument("--json", action="store_true",
                    help="Print the summary as JSON instead of the staged narrative")
    args = ap.parse_args(argv)

    try:
        summary = build_company_list(
            project=args.project, metro=args.metro, industry=args.industry,
            national=args.national, dataset=args.dataset, use_inbox=args.use_inbox,
            print_prompt=args.print_prompt, in_file=args.in_file,
            classify=args.classify, dry_run=args.dry_run)
    except ValueError as e:
        print(f"error: {e}")
        return 2

    if args.json:
        print(json.dumps(summary, indent=2, default=str))
    else:
        _print_narrative(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
