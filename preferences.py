"""The tailoring contract: a free-text profile (preferences.md, read by the AI
ranker) plus cheap hard filters (preferences.json) applied before any AI call.

`load()` returns {"profile_md": str, "hard": dict}. Missing files yield safe,
permissive defaults so a fresh data folder still runs. `hard_gate()` is the cheap
pre-AI cut; `migrate_from_user_config()` seeds the new shape from the legacy
user_config.json.
"""
import json
from pathlib import Path

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
}


def load(prefs_md=None, prefs_json=None) -> dict:
    """Load the preferences contract. prefs_md/prefs_json override the resolved
    paths (for tests). Returns {"profile_md": str, "hard": dict}; absent or
    malformed files fall back to defaults. Paths are resolved per active project
    (root pre-migration) so preferences live beside that project's config/resume."""
    json_default, md_default = workspace.preferences_paths()
    md_path = Path(prefs_md or md_default)
    json_path = Path(prefs_json or json_default)

    try:
        profile_md = md_path.read_text(encoding="utf-8")
    except OSError:
        profile_md = ""

    hard = dict(_DEFAULT_HARD)
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            hard.update({k: data[k] for k in _DEFAULT_HARD if k in data})
    except (OSError, json.JSONDecodeError):
        pass

    return {"profile_md": profile_md, "hard": hard}


def hard_gate(jobs, hard: dict) -> list:
    """Cheap pre-AI filter. Drops a job only when it clearly violates a hard
    constraint; unknowns (no salary, no location) are KEPT so the wide net isn't
    over-cut. Order preserved.

    - salary: drop only when the job has a known salary below `salary_min`.
    - title: drop if it contains a dealbreaker or seniority_exclude substring.
    - location: drop if the job HAS a location that matches none of `locations`,
      unless `remote_ok` and the posting looks remote.
    """
    smin = hard.get("salary_min")
    locations = [s.lower() for s in hard.get("locations", []) if s]
    remote_ok = hard.get("remote_ok", True)
    blockers = [s.lower() for s in
                (list(hard.get("dealbreakers", [])) + list(hard.get("seniority_exclude", [])))
                if s]

    out = []
    for j in jobs:
        title = (getattr(j, "title", "") or "").lower()
        loc = (getattr(j, "location", "") or "").lower()
        sal = getattr(j, "salary_min", None)

        if smin and isinstance(sal, (int, float)) and sal > 0 and sal < smin:
            continue
        if any(b in title for b in blockers):
            continue
        if locations and loc:  # only gate when the job actually states a location
            is_remote = "remote" in loc or "remote" in title
            if not (any(c in loc for c in locations) or (remote_ok and is_remote)):
                continue
        out.append(j)
    return out


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
