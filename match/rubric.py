"""Deterministic ranking rubric — the 'what I want' criteria the gate filters on
and the compact AI request scores against (spec-2026-06-29 §5 Task C).

Built from the structured sources that already exist and are reliable:
  - preferences.json  -> hard floors (salary, dealbreakers, work_auth)
  - user_config.json  -> keywords (target roles), exclude_titles, salary_min
  - preferences.md     -> the free-text profile prose (passed through for the model)

The model-distilled rubric (weighing the prose into explicit boosts) is the
deferred local-model step; this deterministic version is the dependable floor and
keeps the same shape, so the AI request doesn't change when the model lands.
"""
from __future__ import annotations

# Policy defaults — central place to tune the candidate's standing constraints.
_DEFAULT_SENIORITY_TARGET = "entry-mid"
_DEFAULT_YEARS_CAP = 8                # a posting demanding >= this many years is a drop
_DEFAULT_PENALTY_ROLES = ["sales", "maintain", "manage"]


def build_rubric(prefs: dict | None = None, cfg: dict | None = None) -> dict:
    """Assemble the rubric dict from preferences + the project config.

    prefs = preferences.load() ({"profile_md", "hard"}); cfg = the project's
    user_config/config.json. Both are loaded lazily when omitted.
    """
    if prefs is None:
        import preferences as _p
        prefs = _p.load()
    if cfg is None:
        try:
            import workspace
            cfg = workspace.load_config()
        except Exception:
            cfg = {}

    hard = prefs.get("hard", {}) or {}
    comp_floor = cfg.get("salary_min") or hard.get("salary_min")
    target_roles = list(cfg.get("keywords") or hard.get("target_roles") or [])
    hard_no_titles = list(cfg.get("exclude_titles") or []) + list(hard.get("dealbreakers") or [])

    return {
        "comp_floor": int(comp_floor) if comp_floor else None,
        "seniority_target": cfg.get("seniority_target", _DEFAULT_SENIORITY_TARGET),
        "years_cap": int(cfg.get("years_cap", _DEFAULT_YEARS_CAP)),
        "allow_intern": bool(cfg.get("allow_intern", False)),
        "has_clearance": bool(cfg.get("has_clearance", False)),
        "hard_no_titles": [t.lower().strip() for t in hard_no_titles if t and t.strip()],
        "penalty_roles": list(cfg.get("penalty_roles", _DEFAULT_PENALTY_ROLES)),
        "target_roles": target_roles,
        "profile_md": (prefs.get("profile_md") or "").strip(),
    }


def rubric_text(rubric: dict) -> str:
    """A compact rubric block for the AI prompt (criteria first, then the
    free-text profile prose so the model still gets the candidate's voice)."""
    lines = ["## CANDIDATE RUBRIC", ""]
    if rubric.get("target_roles"):
        lines.append("Target roles: " + ", ".join(rubric["target_roles"]))
    lines.append(f"Seniority target: {rubric.get('seniority_target', 'entry-mid')} "
                 f"(a role demanding {rubric.get('years_cap', 8)}+ years is a stretch)")
    if rubric.get("comp_floor"):
        lines.append(f"Comp floor: ${rubric['comp_floor']:,}")
    if rubric.get("hard_no_titles"):
        lines.append("Avoid title types: " + ", ".join(rubric["hard_no_titles"]))
    if rubric.get("penalty_roles"):
        lines.append("Downweight role types: " + ", ".join(rubric["penalty_roles"]))
    lines.append("No security clearance; no internships." if not rubric.get("allow_intern")
                 else "No security clearance.")
    prose = rubric.get("profile_md")
    if prose:
        lines += ["", "### Profile (my own words)", prose]
    return "\n".join(lines)
