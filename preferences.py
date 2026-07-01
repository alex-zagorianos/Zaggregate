"""The tailoring contract: a free-text profile (preferences.md, read by the AI
ranker) plus cheap hard filters (preferences.json) applied before any AI call.

`load()` returns {"profile_md": str, "hard": dict}. Missing files yield safe,
permissive defaults so a fresh data folder still runs. `hard_gate()` is the cheap
pre-AI cut; `migrate_from_user_config()` seeds the new shape from the legacy
user_config.json.
"""
import json
from pathlib import Path
from typing import Optional

import config
import workspace

# Permissive defaults: an empty/absent preferences.json must not silently hide
# jobs. The wide net only narrows on constraints the user actually set.
_DEFAULT_HARD = {
    "salary_min": None,        # int annual floor; None = no floor
    "locations": [],           # acceptable location substrings (city/state); [] = any
    "remote_ok": True,         # keep remote postings even if location doesn't match
    "work_auth": "",           # informational (surfaced to the AI), not gated here
    "dealbreakers": [],        # title substrings that disqualify (e.g. "clearance")
    "seniority_exclude": [],   # title substrings to exclude (e.g. "principal")
    "target_roles": [],        # keyword/role strings seeded from user_config.keywords
    "employment_types": [],    # allowed employment types (empty = any); e.g. ["full-time"]
}


def load(prefs_md=None, prefs_json=None) -> dict:
    """Load the preferences contract. prefs_md/prefs_json override the resolved
    paths (for tests). Returns {"profile_md": str, "hard": dict,
    "fit_preference": str}; absent or malformed files fall back to defaults.
    Paths are resolved per active project (root pre-migration) so preferences
    live beside that project's config/resume.

    `fit_preference` is a per-profile free-text bias woven into every AI-ranking
    route (bridge/API/MCP/file). Default '' = NEUTRAL (no bias sentence at all),
    replacing the app-wide 'prefers smaller companies' text that used to be baked
    into everyone's ranking. Read from preferences.json's 'fit_preference' key."""
    json_default, md_default = workspace.preferences_paths()
    md_path = Path(prefs_md or md_default)
    json_path = Path(prefs_json or json_default)

    try:
        profile_md = md_path.read_text(encoding="utf-8")
    except OSError:
        profile_md = ""

    hard = dict(_DEFAULT_HARD)
    fit_preference = ""
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            hard.update({k: data[k] for k in _DEFAULT_HARD if k in data})
            fp = data.get("fit_preference")
            if isinstance(fp, str):
                fit_preference = fp.strip()
    except (OSError, json.JSONDecodeError):
        pass

    return {"profile_md": profile_md, "hard": hard,
            "fit_preference": fit_preference}


def _location_variants(locations) -> set:
    """Expand each preference location into its metro variants so a prefs entry
    like "Cincinnati, OH" also accepts a posting in "Greater Cincinnati Area".
    Reuses coverage.geography.metro_variants (CBSA-based, agnostic); on any error
    (missing data bundle) it degrades to the bare lowercased entries -- never
    fewer than the substring set the old gate used."""
    variants = set()
    for entry in locations:
        e = (entry or "").strip()
        if not e:
            continue
        variants.add(e.lower())
        # A "City, ST" entry: also index the bare city so "cincinnati" matches
        # postings that drop the state ("Greater Cincinnati Area").
        variants.add(e.split(",")[0].strip().lower())
        try:
            from coverage.geography import metro_variants
            variants |= {v for v in metro_variants(e) if v}
        except Exception:
            pass
    return {v for v in variants if v}


def hard_gate(jobs, hard: dict, *, counts: Optional[dict] = None) -> list:
    """Cheap pre-AI filter. Drops a job only when it clearly violates a hard
    constraint; unknowns (no salary, no location) are KEPT so the wide net isn't
    over-cut. Order preserved.

    - salary: drop only when the job's disclosed MAX-or-min is below `salary_min`
      (aligns with match.comp.meets_floor; a $70k-$120k job no longer dies against
      a $90k floor on its range floor).
    - title: drop if it contains a dealbreaker or seniority_exclude substring.
    - location: drop if the job HAS a location matching none of `locations`
      (metro-variant expanded), unless `remote_ok` and the posting looks remote.
    - employment_type: when the user set `employment_types` (empty = any), drop a
      job whose detected employment_type is present but not in the allowed set.

    `counts`, when passed, is a mutable dict updated with per-reason drop tallies
    ("salary", "title", "location", "employment_type") so callers (daily_run) can
    log why jobs were cut without re-deriving the reasons.
    """
    smin = hard.get("salary_min")
    variants = _location_variants(hard.get("locations", []) or [])
    remote_ok = hard.get("remote_ok", True)
    blockers = [s.lower() for s in
                (list(hard.get("dealbreakers", [])) + list(hard.get("seniority_exclude", [])))
                if s]
    allowed_types = {str(t).strip().lower() for t in (hard.get("employment_types") or []) if t}

    tally = counts if counts is not None else {}
    for k in ("salary", "title", "location", "employment_type"):
        tally.setdefault(k, 0)

    out = []
    for j in jobs:
        title = (getattr(j, "title", "") or "").lower()
        loc = (getattr(j, "location", "") or "").lower()
        smin_j = getattr(j, "salary_min", None)
        smax_j = getattr(j, "salary_max", None)
        top = smax_j if isinstance(smax_j, (int, float)) and smax_j > 0 else smin_j

        if smin and isinstance(top, (int, float)) and top > 0 and top < smin:
            tally["salary"] += 1
            continue
        if any(b in title for b in blockers):
            tally["title"] += 1
            continue
        if variants and loc:  # only gate when the job actually states a location
            is_remote = "remote" in loc or "remote" in title
            if not (any(c in loc for c in variants) or (remote_ok and is_remote)):
                tally["location"] += 1
                continue
        if allowed_types:
            etype = _employment_type_of(j)
            if etype and etype not in allowed_types:
                tally["employment_type"] += 1
                continue
        out.append(j)
    return out


def _employment_type_of(job) -> Optional[str]:
    """Detected employment_type for the gate: prefer an explicit attribute (set by
    a facts pass), else derive from title+description via match.facts. None when
    undetermined (kept -- unknown is not a violation)."""
    et = getattr(job, "employment_type", None)
    if et:
        return str(et).strip().lower()
    try:
        from match.facts import detect_employment_type
        return detect_employment_type(
            getattr(job, "title", "") or "", getattr(job, "description", "") or "")
    except Exception:
        return None


def migrate_from_user_config(cfg: dict) -> dict:
    """Map a legacy user_config.json dict into the new {profile_md, hard} shape.
    Pure function (no I/O) so it's easy to test and reuse during scaffolding."""
    hard = dict(_DEFAULT_HARD)
    if cfg.get("salary_min"):
        hard["salary_min"] = cfg["salary_min"]
    if cfg.get("location"):
        hard["locations"] = [cfg["location"]]
    if cfg.get("exclude_titles"):
        hard["dealbreakers"] = list(cfg["exclude_titles"])
    if cfg.get("seniority_exclude"):
        hard["seniority_exclude"] = list(cfg["seniority_exclude"])

    keywords = cfg.get("keywords") or []
    if keywords:
        hard["target_roles"] = list(keywords)
    lines = [
        "# My Job Preferences",
        "",
        "> Describe the roles you want in plain English. The AI reads this to rank",
        "> and sort jobs to your taste. Be specific about what you love and avoid.",
        "",
    ]
    if keywords:
        lines += ["Target roles / keywords I care about: " + ", ".join(keywords), ""]
    return {"profile_md": "\n".join(lines), "hard": hard}
