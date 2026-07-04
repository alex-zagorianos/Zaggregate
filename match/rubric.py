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

import re

# Policy defaults — central place to tune the candidate's standing constraints.
_DEFAULT_SENIORITY_TARGET = "entry-mid"
_DEFAULT_YEARS_CAP = 8                # a posting demanding >= this many years is a drop
_DEFAULT_PENALTY_ROLES = ["sales", "maintain", "manage"]

# Executive intent, detected from the roles the user is targeting. When present,
# the gate must NOT drop people-management roles or treat senior titles as a
# "stretch", 8+ years stops being disqualifying, AND the seniority_target jumps
# to senior-exec. This adapts the whole pipeline to a VP/Director/Chief seeker
# from the keywords they already typed — no extra onboarding question, no tokens
# spent. Deliberately requires a CLEAR exec modifier (director/VP/chief/president/
# "head of"/"managing director") — bare "manager"/"management" is NOT here (#28):
# a "Product Manager"/"Account Manager"/"Community Manager" seeker is an
# individual contributor, not an executive, and must not get years_cap=25 /
# seniority_target=senior-exec.
_EXEC_RE = re.compile(
    r"\b(chief|c[efimosx]o|cmio|ciso|vp|svp|evp|vice\s+president|president|"
    r"head\s+of|director|executive|managing\s+director)\b",
    re.I)

# People-MANAGEMENT intent (#28): bare "manager"/"management" in the target
# role, e.g. "Engineering Manager"/"Sr. Manager". Distinct from _EXEC_RE — this
# only unlocks allow_management (don't hard-drop people-management postings for
# someone who is themselves targeting a manager title); it does NOT by itself
# push seniority_target to senior-exec or years_cap to 25 (that stays reserved
# for a genuine director/VP/chief target — see _has_exec_intent).
_MANAGEMENT_RE = re.compile(r"\b(manager|management)\b", re.I)

# Individual-contributor titles that happen to CONTAIN "manager"/"management" as
# part of a compound IC role name, not a people-management position (#28):
# "Product Manager", "Account Manager", "Community Manager", "Engagement
# Manager", "Program/Project Manager", social-media/marketing-coordinator-level
# titles. These must NOT trip _MANAGEMENT_RE (no allow_management flip, no
# senior-tier bump) — they read as ordinary IC keywords.
_IC_MANAGER_COMPOUND_RE = re.compile(
    r"\b(product|program|project|account|community|social\s+media|marketing|"
    r"brand|customer\s+success|vendor|category|engagement|partner(?:ship)?|"
    r"client)\s+manager\b",
    re.I)


def _is_ic_manager_compound(role: str) -> bool:
    """True when every 'manager'/'management' mention in `role` is part of a
    known IC-compound title (Product Manager, Account Manager, ...), so the
    bare-word management match should be suppressed."""
    role = role or ""
    if not _MANAGEMENT_RE.search(role):
        return False
    stripped = _IC_MANAGER_COMPOUND_RE.sub("", role)
    return not _MANAGEMENT_RE.search(stripped)


# A "senior" (but non-exec) target: a 15-year senior IC's own tier. Raises the
# years cap from 8 to 15 so a "10+ years" senior posting still reaches AI ranking
# instead of being dropped for demanding too many years.
_SENIOR_RE = re.compile(r"\b(senior|sr\.?|staff|principal|lead|expert)\b", re.I)
_SENIOR_YEARS_CAP = 15


def _has_exec_intent(target_roles) -> bool:
    return any(_EXEC_RE.search(r or "") for r in target_roles)


def _has_management_intent(target_roles) -> bool:
    """True when a target role carries genuine people-management intent (a bare
    'manager'/'management' title that is NOT one of the known IC compounds).
    "Engineering Manager"/"Sr. Manager" -> True; "Product Manager" -> False."""
    for r in target_roles:
        r = r or ""
        if _MANAGEMENT_RE.search(r) and not _is_ic_manager_compound(r):
            return True
    return False


def _has_senior_intent(target_roles) -> bool:
    return any(_SENIOR_RE.search(r or "") for r in target_roles)


def _field_adjust_penalty_roles(base_penalties: list, cfg: dict) -> list:
    """Drop the penalty role that IS the user's own field's core work (item 10):
    a maintenance tech (SOC 49) keeps "maintain", a salesperson (SOC 41) keeps
    "sales". Derived from the project's persisted onet_soc_code (preferred) or its
    free-text industry, via industry_profile.penalty_role_to_drop. Default (eng /
    unmapped) is unchanged."""
    try:
        import industry_profile
        drop = industry_profile.penalty_role_to_drop(
            soc_code=cfg.get("onet_soc_code"), industry=cfg.get("industry"))
    except Exception:
        drop = None
    if not drop:
        return list(base_penalties)
    return [r for r in base_penalties if r != drop]


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

    # Adapt to a management/executive seeker (inferred from their target roles,
    # e.g. "VP Health Informatics"), unless the config overrides explicitly. This
    # flips the entry-mid IC defaults that would otherwise drop every VP/Director
    # role before the AI ever sees it.
    #
    # #28 fix: exec_intent (true exec tokens: director/VP/chief/president/"head
    # of"/managing director) and management_intent (bare "manager"/"management",
    # EXCLUDING known IC-compound titles like "Product Manager") are now separate
    # signals. allow_management is unlocked by EITHER (a people-management-title
    # seeker, like an exec seeker, must not have the gate hard-drop management
    # postings) — but only exec_intent bumps seniority_target to senior-exec /
    # years_cap to 25. A bare "Engineering Manager" seeker instead lands on the
    # SENIOR (non-exec) tier via management_intent (mirroring _has_senior_intent),
    # and a "Product Manager"/"Account Manager"/"Community Manager" IC seeker
    # trips neither signal at all — fully unchanged entry-mid defaults (parity).
    exec_intent = _has_exec_intent(target_roles)
    management_intent = _has_management_intent(target_roles)
    senior_intent = _has_senior_intent(target_roles) or management_intent
    allow_management = bool(cfg.get("allow_management", exec_intent or management_intent))
    seniority_target = cfg.get("seniority_target") or (
        "senior-exec" if exec_intent else
        ("senior" if senior_intent else _DEFAULT_SENIORITY_TARGET))
    # years cap: exec 25, senior/management (non-exec) 15, else the default 8. A
    # senior IC's own tier ("10+ years" postings) must still reach AI ranking
    # (item 9); a people-management (non-exec) seeker gets the same tier (#28).
    if exec_intent:
        default_cap = 25
    elif senior_intent:
        default_cap = _SENIOR_YEARS_CAP
    else:
        default_cap = _DEFAULT_YEARS_CAP
    years_cap = int(cfg.get("years_cap", default_cap))
    penalty_roles = cfg.get("penalty_roles")
    if penalty_roles is None:
        # An exec or people-management seeker should not be penalized for "manage".
        base_penalties = (["sales", "maintain"] if (exec_intent or management_intent)
                          else list(_DEFAULT_PENALTY_ROLES))
        # Field-aware (item 10): a field whose OWN core work is a penalty role
        # (a maintenance tech's "maintain", a salesperson's "sales") must not have
        # that role downweighted. Drop the field's core penalty role by SOC major
        # group; default unchanged.
        penalty_roles = _field_adjust_penalty_roles(base_penalties, cfg)

    return {
        "comp_floor": int(comp_floor) if comp_floor else None,
        "seniority_target": seniority_target,
        "years_cap": years_cap,
        "allow_intern": bool(cfg.get("allow_intern", False)),
        "allow_management": allow_management,
        "has_clearance": bool(cfg.get("has_clearance", False)),
        "hard_no_titles": [t.lower().strip() for t in hard_no_titles if t and t.strip()],
        "penalty_roles": list(penalty_roles),
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
