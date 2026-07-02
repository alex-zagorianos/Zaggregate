"""AI-assisted setup ("Set me up with my AI") — the BYO-AI onboarding path.

The app never calls an LLM itself (BYO-AI / clipboard bridge is the whole moat).
Instead this module builds a copyable PROMPT the user pastes — together with
their résumé and one sentence of intent — into THEIR OWN AI (Claude/ChatGPT).
The AI emits a canonical fenced config block; the user pastes it back; a strict
parser here validates it and applies it to the project's config.json +
preferences.{json,md}.

Two prompt/parse pairs live here:

  1. PROFILE setup (§6.3): résumé + intent -> a config block (field token,
     target titles, location, salary floor, seniority, remote pref, radius, plus
     a natural-language preferences.md profile). `build_setup_prompt()` /
     `parse_setup_block()` / `apply_setup()`.

  2. COMPANY seeding (§6.7 / SB-2a): the persona tests proved AI slug-guessing is
     ~50% wrong but careers-PAGE URLs are what AIs get right, so the seeding
     prompt asks for careers-page URLs ONLY. `build_seed_prompt()`; parsing stays
     the existing `Name | URL` pipeline (scrape.ats_detect.parse_line) + the P0-6
     verified-by-default gate. `apply_seed_lines()` runs detect/probe/save.

Everything here is pure/side-effect-scoped and import-safe (no tkinter at module
scope) so both the GUI dialog and tests/MCP can call the functions directly.
"""
from __future__ import annotations

import json

import industry_profile
import workspace


# ── the config-block vocabulary ───────────────────────────────────────────────
# The canonical FIELD tokens the AI must choose from. Sourced from the shipped
# industry_profile seed rules so a returned token routes sources/rankings
# correctly (the wizard's fragile free-text field is exactly what caused the
# multi-word routing bug). "other" is the escape hatch -> generic full reach.
CANONICAL_FIELDS: list[str] = [
    "software engineering", "engineering", "data analytics", "marketing",
    "digital marketing", "finance", "sales", "healthcare", "nursing",
    "education", "teaching", "legal", "human resources", "consulting",
    "warehouse", "logistics", "operations", "design", "construction",
    "hospitality", "energy", "fitness", "customer support", "management",
    "other",
]

# Canonical seniority tokens (mapped to the wizard's level -> rubric config).
CANONICAL_SENIORITY: list[str] = ["entry", "mid", "senior", "manager"]

# Map a canonical seniority token to the wizard's level label (reused so the
# AI path and the wizard produce identical rubric config via _level_to_config).
_SENIORITY_TO_LEVEL = {
    "entry": "Entry", "mid": "Mid", "senior": "Senior", "manager": "Manager/Exec",
}


class SetupBlockError(ValueError):
    """The pasted config block was missing, unparseable, or failed validation.
    Carries a human-actionable message (shown verbatim in the dialog)."""


# ── prompt generation (profile setup) ─────────────────────────────────────────
def build_setup_prompt() -> str:
    """The copyable prompt the user pastes into THEIR AI, above their résumé +
    one sentence of intent. Instructs the AI to emit a single fenced JSON config
    block in the documented vocabulary. Static (no secrets, no I/O)."""
    fields = ", ".join(CANONICAL_FIELDS)
    return (
        "You are setting up a job-search app for me. Below this prompt I will "
        "paste my RÉSUMÉ and ONE SENTENCE describing the job I want.\n\n"
        "Read them and return ONLY a single fenced code block (```json ... ```) "
        "with EXACTLY these keys — no prose before or after:\n\n"
        "```json\n"
        "{\n"
        '  "field": "<ONE token, chosen ONLY from this list: ' + fields + '>",\n'
        '  "target_titles": ["<job title I should search for>", "..."],\n'
        '  "location": "<City, ST>  (or "Remote" if I want remote-only)",\n'
        '  "remote_ok": true,\n'
        '  "radius_miles": 50,\n'
        '  "salary_floor": 0,\n'
        '  "seniority": "<one of: entry, mid, senior, manager>",\n'
        '  "preferences_md": "<2-5 sentences, first person, describing the roles '
        "I want, what I love, and any dealbreakers — this is read by an AI to "
        'rank jobs to my taste>"\n'
        "}\n"
        "```\n\n"
        "Rules:\n"
        "- \"field\" MUST be exactly one token from the list above. If nothing "
        "fits, use \"other\".\n"
        "- \"target_titles\": 1-5 real job titles (strings).\n"
        "- \"location\": my metro as \"City, ST\", or the literal \"Remote\" for "
        "remote-only.\n"
        "- \"salary_floor\": my minimum acceptable ANNUAL salary in whole US "
        "dollars (0 if I don't care).\n"
        "- \"radius_miles\": how far from my location I'll commute (whole miles).\n"
        "- Return the block ONLY. Do not invent facts not supported by my résumé "
        "or sentence.\n\n"
        "--- paste your résumé and one sentence of intent below this line ---\n"
    )


# ── strict parser + validation (profile setup) ────────────────────────────────
def _canonical_field(raw: str) -> str:
    """Validate/normalize the AI's field token against the canonical vocabulary
    (via the registry's _normalize_industry + industry_profile). Returns the
    matched canonical token, or raises SetupBlockError with an actionable list.
    'other' is accepted as the explicit generic-reach escape hatch."""
    from scrape.company_registry import _normalize_industry
    val = (raw or "").strip()
    if not val:
        raise SetupBlockError(
            "The config block is missing a 'field'. Re-run the prompt, or set "
            "your field manually in Setup.")
    norm = _normalize_industry(val)                       # e.g. "Data Analytics" -> data_analytics
    canon_norm = {_normalize_industry(c): c for c in CANONICAL_FIELDS}
    if norm in canon_norm:
        return canon_norm[norm]
    # Accept a token that at least resolves to a known seed profile (so a close
    # synonym like "registered nurse" or "management consulting" is tolerated) —
    # but only when it lands on a NON-generic seed, so a typo can't slip through.
    try:
        prof = industry_profile.resolve(val)
    except Exception:
        prof = None
    if prof is not None and prof.source in ("seed", "user"):
        return val.strip().lower()
    raise SetupBlockError(
        f"Unknown field {raw!r}. Ask your AI to pick ONE token from: "
        + ", ".join(CANONICAL_FIELDS))


def _validate_titles(raw) -> list[str]:
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        raise SetupBlockError(
            "'target_titles' must be a list of job-title strings.")
    titles = [str(t).strip() for t in raw if str(t).strip()]
    if not titles:
        raise SetupBlockError(
            "'target_titles' is empty — the AI must return at least one job title.")
    return titles


def _validate_salary(raw) -> int | None:
    if raw in (None, "", 0, "0"):
        return None
    try:
        val = int(round(float(str(raw).replace(",", "").replace("$", "").strip())))
    except (TypeError, ValueError):
        raise SetupBlockError(
            f"'salary_floor' must be a number (got {raw!r}).")
    return val if val > 0 else None


def _validate_radius(raw) -> int | None:
    if raw in (None, "", 0, "0"):
        return None
    try:
        val = int(round(float(str(raw).replace(",", "").strip())))
    except (TypeError, ValueError):
        raise SetupBlockError(f"'radius_miles' must be a whole number (got {raw!r}).")
    return val if val > 0 else None


def _validate_seniority(raw) -> str:
    """Return the wizard LEVEL label for a canonical seniority token, or '' when
    absent/blank. Unknown non-blank tokens raise (actionable)."""
    val = (str(raw or "")).strip().lower()
    if not val:
        return ""
    # Tolerate a few common phrasings.
    alias = {"junior": "entry", "entry-level": "entry", "mid-level": "mid",
             "manager/exec": "manager", "executive": "manager", "lead": "senior",
             "staff": "senior", "principal": "senior"}
    val = alias.get(val, val)
    if val not in _SENIORITY_TO_LEVEL:
        raise SetupBlockError(
            f"'seniority' must be one of {CANONICAL_SENIORITY} (got {raw!r}).")
    return _SENIORITY_TO_LEVEL[val]


def parse_setup_block(text: str) -> dict:
    """Parse + STRICTLY validate the pasted config block into a wizard `answers`
    dict (so apply_setup can reuse setup_wizard.build_preferences/_search_config
    — one contract, no drift). Raises SetupBlockError with an actionable message
    on any problem. Never partially applies (pure parse; caller applies)."""
    from claude_bridge import _extract_json
    if not (text or "").strip():
        raise SetupBlockError("Nothing pasted — copy your AI's reply first.")
    try:
        payload = json.loads(_extract_json(text, prefer="object"))
    except (json.JSONDecodeError, ValueError):
        raise SetupBlockError(
            "Couldn't find a valid JSON config block in the pasted text. Make "
            "sure you copied the ```json ... ``` block your AI returned.")
    if not isinstance(payload, dict):
        raise SetupBlockError(
            "The config block must be a JSON object with the documented keys.")

    field = _canonical_field(payload.get("field", ""))
    titles = _validate_titles(payload.get("target_titles"))
    location_raw = str(payload.get("location") or "").strip()
    remote_only = location_raw.lower() in ("remote", "remote-only", "remote only")
    # remote_ok defaults True; a remote-only location implies remote_ok.
    remote_ok = bool(payload.get("remote_ok", True)) or remote_only
    salary = _validate_salary(payload.get("salary_floor"))
    radius = _validate_radius(payload.get("radius_miles"))
    level = _validate_seniority(payload.get("seniority"))
    about = str(payload.get("preferences_md") or "").strip()

    # Map to the wizard's `answers` contract (build_preferences/_search_config).
    # The industry token is the canonical `field` (routes sources/rankings); a
    # remote-only location is stored as "Remote" so the search config records it.
    answers = {
        "roles": titles,
        "location": "Remote" if remote_only else location_raw,
        "remote_ok": remote_ok,
        "salary_min": salary,
        "industry": field if field != "other" else "",
        "level": level,
        "about": about,
    }
    # Non-`answers` extras the AI-setup applies directly to config.json.
    extras = {"radius": radius, "remote_only": remote_only,
              "field_token": field, "target_titles": titles}
    return {"answers": answers, "extras": extras}


def apply_setup(text: str, *, mark_onboarded: bool = True) -> dict:
    """Parse the pasted config block and APPLY it: write the active project's
    config.json (search config) + preferences.{json,md} via the SAME shared
    helpers the wizard uses (setup_wizard.build_preferences/_search_config +
    workspace.scaffold_preferences), so the AI path and the wizard produce an
    identical on-disk contract. Returns a small summary dict for the UI. Raises
    SetupBlockError (unapplied) on any validation problem."""
    from ui import setup_wizard
    parsed = parse_setup_block(text)                       # may raise (pre-apply)
    answers = parsed["answers"]
    extras = parsed["extras"]

    prefs = setup_wizard.build_preferences(answers)
    workspace.scaffold_preferences(hard=prefs["hard"],
                                   profile_md=prefs["profile_md"])

    cfg = setup_wizard._search_config(answers, workspace.load_config())
    if extras.get("radius"):
        cfg["radius"] = extras["radius"]
    workspace.save_config(cfg)

    if mark_onboarded:
        setup_wizard.mark_onboarded()

    return {
        "field": extras["field_token"],
        "target_titles": extras["target_titles"],
        "location": answers["location"],
        "remote_only": extras["remote_only"],
        "salary_min": answers["salary_min"],
        "seniority": answers["level"],
        "radius": extras.get("radius"),
        "profile_chars": len(prefs["profile_md"]),
    }


# ── company seeding prompt (§6.7 / SB-2a) — careers-page URLs ONLY ─────────────
def build_seed_prompt(field: str = "", metro: str = "", *, limit: int = 30) -> str:
    """The copyable prompt for AI-assisted company seeding. Per the persona
    evidence (AI slug-guessing ~50% wrong, careers-PAGE URLs reliably right), it
    asks the AI for `Name | careers-page URL` lines ONLY — the app's own ATS
    detector (scrape.ats_detect, now incl. workday_cxs) resolves the slug, and
    the P0-6 verified-by-default gate drops anything that fails its live probe.
    Static; safe to show with blank field/metro (generic wording)."""
    who = (field or "").strip() or "my field"
    where = (metro or "").strip() or "my area"
    return (
        f"List up to {limit} of the largest employers of {who} workers in "
        f"{where} (include nearby suburbs; a mix of sizes).\n\n"
        "For EACH employer, give me its NAME and the URL of its CAREERS / jobs "
        "page — the page that lists open positions (e.g. a Greenhouse, Lever, "
        "Ashby, SmartRecruiters, or Workday careers page, or the company's own "
        "'/careers' page). I need the careers-page URL, NOT the homepage, and "
        "NOT an ATS tenant/slug string (I can't verify those).\n\n"
        "Return ONLY lines in this exact format, one per line, no prose:\n"
        "  Company Name | https://careers-page-url\n\n"
        "If you're unsure of a company's careers-page URL, give its main website "
        "instead of guessing — the app verifies every link and quietly drops any "
        "that aren't live, so a wrong guess can't break anything."
    )


def apply_seed_lines(text: str, *, industry: str = "", probe: bool = True) -> dict:
    """Parse pasted `Name | URL` (or bare-URL) lines, detect the ATS/slug, probe
    each board live, and save with the P0-6 verified-by-default gate. Returns
    per-line verdicts + counts. Pure of the GUI (reused by the MCP seed_companies
    tool). `probe=False` skips the live probe (offline/tests) — then no board is
    treated as verified, so unverified boards are still gated out of scraping.

    Verdict per line: 'live'/'direct' -> verified & saved; 'unreachable' ->
    flagged-unverified (saved but excluded from scraping until it verifies);
    'skipped' -> already in the registry; 'rejected' -> a ToS-blocked/aggregator
    host (NEOGOV/governmentjobs, Frontline/AppliTrack, Indeed, LinkedIn, ...)
    that must never be scraped, dropped without saving."""
    from scrape.ats_detect import parse_line, probe_count, is_tos_blocked_host
    from scrape.company_registry import (UNVERIFIED_FLAG, is_unverified,
                                         save_companies, get_registry)

    lines = [ln for ln in (text or "").splitlines() if ln.strip()]
    entries = [e for e in (parse_line(ln) for ln in lines) if e]
    ind = (industry or "").strip()
    for e in entries:
        e.industries = [ind] if ind else []

    # Existing registry names, so we can report already-present. A currently
    # UNVERIFIED stored board is NOT treated as "already in registry": a fresh
    # live/direct verdict must flow through to save_companies so the P0-6
    # re-verify upgrade can clear its flag (otherwise a mis-guessed-then-
    # corrected board stays permanently unscraped). Only VERIFIED stored boards
    # short-circuit as skipped.
    try:
        _all = get_registry(include_unverified=True)
        known = {(c.name or "").lower() for c in _all if not is_unverified(c)}
    except Exception:
        known = set()

    verdicts: list[dict] = []
    to_save = []
    for e in entries:
        # ToS/aggregator guard: a NEOGOV/governmentjobs, Frontline/AppliTrack,
        # Indeed, LinkedIn, etc. URL must NEVER enter the scraped registry. These
        # always fall to 'direct' (their host matches no ATS), where the slug IS
        # the full URL, so the daily direct-scraper would plain-GET it. Reject at
        # save time — critical for the AI-drivable MCP seed_companies path, where
        # an agent could otherwise seed an arbitrary (ToS-gray) fetch target.
        if is_tos_blocked_host(e.slug):
            verdicts.append({"name": e.name, "ats_type": e.ats_type,
                             "slug": e.slug, "verdict": "rejected",
                             "detail": "blocked host (ToS/aggregator — not saved)"})
            continue
        if (e.name or "").lower() in known:
            verdicts.append({"name": e.name, "ats_type": e.ats_type,
                             "slug": e.slug, "verdict": "skipped",
                             "detail": "already in registry"})
            continue
        if e.ats_type == "direct":
            # The user gave the exact careers page -> verified-manual (uncountable).
            verdicts.append({"name": e.name, "ats_type": e.ats_type,
                             "slug": e.slug, "verdict": "direct",
                             "detail": "saved (direct page)"})
            to_save.append(e)
            continue
        n = probe_count(e) if probe else None
        if n is not None:
            verdicts.append({"name": e.name, "ats_type": e.ats_type,
                             "slug": e.slug, "verdict": "live", "count": n,
                             "detail": f"live ({n} open jobs)"})
            to_save.append(e)
        else:
            e.extra = dict(getattr(e, "extra", None) or {})
            e.extra[UNVERIFIED_FLAG] = True
            verdicts.append({"name": e.name, "ats_type": e.ats_type,
                             "slug": e.slug, "verdict": "unreachable",
                             "detail": "saved unverified (not scraped until it "
                                       "verifies)"})
            to_save.append(e)

    added = save_companies(to_save) if to_save else 0
    verified = sum(1 for v in verdicts if v["verdict"] in ("live", "direct"))
    unverified = sum(1 for v in verdicts if v["verdict"] == "unreachable")
    skipped = sum(1 for v in verdicts if v["verdict"] == "skipped")
    rejected = sum(1 for v in verdicts if v["verdict"] == "rejected")
    return {
        "parsed": len(entries), "added": added, "verified": verified,
        "unverified": unverified, "skipped": skipped, "rejected": rejected,
        "verdicts": verdicts,
    }
