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
import re

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
def _config_block_body() -> str:
    """The CONFIG-block half of the setup prompt: the fenced ```json contract +
    its per-key rules. Extracted so ``build_setup_prompt`` (config only) and
    ``build_full_setup_prompt`` (config + seeds) share ONE vocabulary — the field
    list, key schema, and rules can never drift between the two prompts (the whole
    point of the S40 refactor). Ends WITHOUT a trailing paste-line so the caller
    decides what follows (the résumé line, or a second seeds block)."""
    fields = ", ".join(CANONICAL_FIELDS)
    return (
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
        "- \"field\" MUST be exactly one token from the list above. Pick the "
        "closest fit; if my occupation isn't obviously one of them (e.g. a skilled "
        "trade, a niche role), use \"other\" rather than forcing a wrong token.\n"
        "- \"target_titles\": 1-5 real job titles, as a JSON array of strings "
        "(e.g. [\"Forklift Operator\", \"Warehouse Associate\"]).\n"
        "- \"location\": my metro. Use \"City, ST\" for US, \"City, Country\" "
        "outside the US, or the literal \"Remote\" for remote-only.\n"
        "- \"salary_floor\": my minimum acceptable ANNUAL salary as a plain whole "
        "number (e.g. 140000, not \"$140k\"); use 0 if I don't care.\n"
        "- \"radius_miles\": how far from my location I'll commute, as a whole "
        "number (e.g. 50).\n"
        "- Return the block ONLY. Do not invent facts not supported by my résumé "
        "or sentence.\n"
    )


def build_setup_prompt() -> str:
    """The copyable prompt the user pastes into THEIR AI, above their résumé +
    one sentence of intent. Instructs the AI to emit a single fenced JSON config
    block in the documented vocabulary. Static (no secrets, no I/O)."""
    return (
        "You are setting up a job-search app for me. Below this prompt I will "
        "paste my RÉSUMÉ and ONE SENTENCE describing the job I want.\n\n"
        + _config_block_body()
        + "\n--- paste your résumé and one sentence of intent below this line ---\n"
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
    # Accept a token that resolves to a known NON-generic profile (so a close
    # synonym like "registered nurse" or "management consulting", or a real
    # blue-collar occupation the O*NET tier recognizes like "machinist" /
    # "barista" / "welder", is tolerated). Only "generic" (a typo like "quantum
    # astrology" that matches nothing) is rejected — accepting an O*NET-routed
    # occupation is a strict breadth win and keeps the trades audience unblocked.
    try:
        prof = industry_profile.resolve(val)
    except Exception:
        prof = None
    if prof is not None and prof.source in ("seed", "user", "onet"):
        return val.strip().lower()
    raise SetupBlockError(
        f"Unknown field {raw!r}. Ask your AI to pick ONE token from: "
        + ", ".join(CANONICAL_FIELDS))


def _coerce_number(raw, *, allow_k: bool = True) -> float | None:
    """Best-effort human-number parse for weak-AI shorthand. Returns the first
    numeric value in the string, honouring a k/m multiplier when allow_k:
      '140k' -> 140000 · '$120,000 per year' -> 120000 · '1.4m' -> 1400000 ·
      '100000-150000' -> 100000 (low end of a range) · '25 miles' -> 25.
    Returns None only when there is no digit at all (caller decides if that
    is an error)."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    s = str(raw).strip().lower().replace(",", "").replace("$", "")
    if not s:
        return None
    m = re.search(r"(\d+(?:\.\d+)?)\s*([km])?", s)
    if not m:
        return None
    val = float(m.group(1))
    suf = m.group(2)
    if allow_k and suf == "k":
        val *= 1_000
    elif allow_k and suf == "m":
        val *= 1_000_000
    return val


def _validate_titles(raw) -> list[str]:
    # A weak AI sometimes returns a single comma/semicolon/newline-joined STRING
    # instead of a JSON list ("Account Exec, SDR, BDR") — split it so each title
    # is searchable instead of matching nothing as one literal string.
    if isinstance(raw, str):
        parts = [p.strip() for p in re.split(r"[,;\n]+", raw) if p.strip()]
        raw = parts or [raw]
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
    val = _coerce_number(raw, allow_k=True)       # "140k", "$120,000/yr", ranges
    if val is None:
        raise SetupBlockError(
            f"'salary_floor' must be a number (got {raw!r}).")
    ival = int(round(val))
    return ival if ival > 0 else None


def _validate_radius(raw) -> int | None:
    if raw in (None, "", 0, "0"):
        return None
    val = _coerce_number(raw, allow_k=False)      # "25 miles" -> 25
    if val is None:
        raise SetupBlockError(f"'radius_miles' must be a whole number (got {raw!r}).")
    ival = int(round(val))
    return ival if ival > 0 else None


def _validate_seniority(raw) -> str:
    """Return the wizard LEVEL label for a canonical seniority token, or '' when
    absent/blank. Unknown non-blank tokens raise (actionable)."""
    val = (str(raw or "")).strip().lower()
    if not val:
        return ""
    # Tolerate the phrasings a résumé-summarizing AI plausibly emits.
    alias = {"junior": "entry", "entry-level": "entry", "entry level": "entry",
             "intern": "entry", "internship": "entry", "new grad": "entry",
             "new-grad": "entry", "graduate": "entry", "trainee": "entry",
             "mid-level": "mid", "mid level": "mid", "intermediate": "mid",
             "associate": "mid", "manager/exec": "manager", "executive": "manager",
             "exec": "manager", "director": "manager", "vp": "manager",
             "vice president": "manager", "head": "manager", "chief": "manager",
             "c-level": "manager", "c-suite": "manager", "cxo": "manager",
             "ceo": "manager", "cto": "manager", "cfo": "manager", "coo": "manager",
             "lead": "senior", "staff": "senior", "principal": "senior", "sr": "senior"}
    val = alias.get(val, val)
    if val not in _SENIORITY_TO_LEVEL:
        raise SetupBlockError(
            f"'seniority' must be one of {CANONICAL_SENIORITY} (got {raw!r}).")
    return _SENIORITY_TO_LEVEL[val]


# Keys the config block is expected to carry — used to pick the RIGHT object when
# a weak AI emits more than one JSON block (a partial example then the real one).
_EXPECTED_CFG_KEYS = frozenset({
    "field", "target_titles", "location", "remote_ok", "radius_miles",
    "salary_floor", "seniority", "preferences_md"})


def _normalize_pasted(text: str) -> str:
    """Make a pasted AI reply more parse-tolerant: curly/smart quotes -> straight
    (many models render them when formatting markdown, which breaks json.loads),
    and strip // line and /* */ block comments some models annotate JSON with. A
    URL's '//' is preserved (it is never preceded by whitespace/line-start)."""
    t = (text or "")
    t = (t.replace("“", '"').replace("”", '"')
           .replace("‘", "'").replace("’", "'"))
    t = re.sub(r"(?m)(^|\s)//.*$", r"\1", t)
    t = re.sub(r"/\*.*?\*/", "", t, flags=re.S)
    return t


def _best_config_object(text: str):
    """Return the dict most likely to BE the config block. Handles a reply with
    MULTIPLE JSON objects/fences by scoring each brace-balanced candidate on how
    many expected config keys it carries (so a partial `{"field":"sales"}` example
    never wins over the real, complete block). Falls back to the tolerant
    single-object extractor (trailing commas etc.) when no candidate parses."""
    candidates = []
    depth, start = 0, None
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}" and depth > 0:
            depth -= 1
            if depth == 0 and start is not None:
                try:
                    obj = json.loads(text[start:i + 1])
                    if isinstance(obj, dict):
                        candidates.append(obj)
                except (json.JSONDecodeError, ValueError):
                    pass
                start = None
    if candidates:
        candidates.sort(
            key=lambda d: len(_EXPECTED_CFG_KEYS & set(d.keys())), reverse=True)
        return candidates[0]
    # No brace-balanced object parsed. Fall back to the tolerant single-value
    # extractor and return whatever it yields (dict or not) so the caller can
    # tell "no JSON at all" (None) from "JSON, but not an object" (e.g. a list).
    from claude_bridge import _extract_json
    try:
        return json.loads(_extract_json(text, prefer="object"))
    except (json.JSONDecodeError, ValueError):
        return None


def parse_setup_block(text: str) -> dict:
    """Parse + STRICTLY validate the pasted config block into a wizard `answers`
    dict (so apply_setup can reuse setup_wizard.build_preferences/_search_config
    — one contract, no drift). Raises SetupBlockError with an actionable message
    on any problem. Never partially applies (pure parse; caller applies)."""
    if not (text or "").strip():
        raise SetupBlockError("Nothing pasted — copy your AI's reply first.")
    payload = _best_config_object(_normalize_pasted(text))
    if payload is None:
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
    # Use the Tk-free core (build_preferences/_search_config/mark_onboarded live
    # there since the S36 split) so the web AI-setup express lane never imports
    # tkinter. The tk setup_wizard re-exports these same objects, so behavior is
    # byte-identical whether called from the GUI or the web API.
    from ui import setup_wizard_core as setup_wizard
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
    else:
        # Config saved mid-wizard: suppress is_onboarded's keyword inference
        # until the wizard actually finishes (mark_onboarded clears this).
        setup_wizard.mark_wizard_in_progress()

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
def _seed_block_body(field: str = "", metro: str = "", *, limit: int = 30,
                     fenced: bool = False) -> str:
    """The careers-page seeding wording (§6.7 / SB-2a): asks for `Name | URL`
    lines ONLY (persona evidence — AI slug-guessing ~50% wrong, careers-PAGE URLs
    reliably right). Extracted so the standalone ``build_seed_prompt`` and the
    combined ``build_full_setup_prompt`` share ONE careers-page vocabulary (no
    fork). ``fenced=True`` wraps the requested lines in a ```seeds fence so the
    combined reply's config and seeds are unambiguously separable by
    ``split_full_reply`` even when a chatty AI adds prose around them."""
    who = (field or "").strip() or "my field"
    where = (metro or "").strip() or "my area"
    if fenced:
        fmt = ("Return ONLY a fenced code block labeled `seeds`, one employer per "
               "line inside it, no prose:\n"
               "```seeds\n"
               "Company Name | https://careers-page-url\n"
               "```\n\n")
    else:
        fmt = ("Return ONLY lines in this exact format, one per line, no prose:\n"
               "  Company Name | https://careers-page-url\n\n")
    return (
        f"List up to {limit} of the largest employers of {who} workers in "
        f"{where} (include nearby suburbs; a mix of sizes).\n\n"
        "For EACH employer, give me its NAME and the URL of its CAREERS / jobs "
        "page — the page that lists open positions (e.g. a Greenhouse, Lever, "
        "Ashby, SmartRecruiters, or Workday careers page, or the company's own "
        "'/careers' page). I need the careers-page URL, NOT the homepage, and "
        "NOT an ATS tenant/slug string (I can't verify those).\n\n"
        + fmt +
        "If you're unsure of a company's careers-page URL, give its main website "
        "instead of guessing — the app verifies every link and quietly drops any "
        "that aren't live, so a wrong guess can't break anything."
    )


def build_seed_prompt(field: str = "", metro: str = "", *, limit: int = 30) -> str:
    """The copyable prompt for AI-assisted company seeding. Per the persona
    evidence (AI slug-guessing ~50% wrong, careers-PAGE URLs reliably right), it
    asks the AI for `Name | careers-page URL` lines ONLY — the app's own ATS
    detector (scrape.ats_detect, now incl. workday_cxs) resolves the slug, and
    the P0-6 verified-by-default gate drops anything that fails its live probe.
    Static; safe to show with blank field/metro (generic wording)."""
    return _seed_block_body(field, metro, limit=limit, fenced=False)


# ── combined config + seeds prompt (S40 AI-first setup) ────────────────────────
def build_full_setup_prompt(field: str = "", metro: str = "", *,
                            seed_limit: int = 25) -> str:
    """The ONE copyable prompt for AI-first setup: it asks the user's own AI for
    BOTH the search config (the exact ```json contract ``build_setup_prompt``
    uses) AND a starter company registry (a ```seeds fence of `Name | careers-URL`
    lines, wording lifted from ``build_seed_prompt``). One paste of the reply then
    drives the whole first-run setup — config + seeded companies + first search.

    Order is JSON block FIRST, seeds block SECOND (``split_full_reply`` relies on
    the config living in the JSON, and treats pipe-shaped lines as seeds only
    outside it). ``field``/``metro`` are optional context for the seeds ask; blank
    is safe (generic wording, and the AI reads the résumé for the field anyway).
    Static — no secrets, no I/O."""
    return (
        "You are setting up a job-search app for me. Below this prompt I will "
        "paste my RÉSUMÉ and ONE SENTENCE describing the job I want.\n\n"
        "Do TWO things and return BOTH blocks, the JSON block FIRST:\n\n"
        "1) A search-config block:\n\n"
        + _config_block_body()
        + "\n2) A starter list of employers to search:\n\n"
        + _seed_block_body(field, metro, limit=seed_limit, fenced=True)
        + "\n\n--- paste your résumé and one sentence of intent below this line ---\n"
    )


# ── combined-reply splitter (S40 AI-first setup) ───────────────────────────────
# A pasted careers line is `Name | http…`. Matched OUTSIDE the chosen JSON block
# so a pipe character living INSIDE the JSON (e.g. a preferences_md sentence with
# "sales | marketing") is never mistaken for a seed line.
_SEED_LINE_RE = re.compile(r"^\s*[^|]+\|\s*https?://\S", re.IGNORECASE)
# The ```seeds fence the combined prompt requests. The label is optional-tolerant
# (a weak AI may drop it), but when present we take EXACTLY that fence's body so
# stray pipe-lines elsewhere in the prose can't pollute the seed set.
_SEEDS_FENCE_RE = re.compile(r"```seeds[^\n]*\n(.*?)```", re.IGNORECASE | re.DOTALL)


def split_full_reply(text: str) -> tuple[str, str]:
    """Split a combined AI reply into ``(config_json_text, seed_lines_text)``.

    * ``config_json_text`` — the best config OBJECT re-serialized as JSON (via the
      same ``_best_config_object`` scorer ``parse_setup_block`` uses, so the config
      half is parsed identically whether it arrived alone or combined). ``""`` when
      no JSON object is present.
    * ``seed_lines_text`` — the ```seeds fence body when present; otherwise every
      ``Name | http…``-shaped line found OUTSIDE the chosen JSON block (so a pipe
      inside the JSON is never treated as a seed). ``""`` when neither yields lines.

    NEVER raises — a junk/empty/partial reply degrades to ``("", "")`` (or a
    config-only / seeds-only pair). Applying is the caller's job; this only
    separates the two halves so each can flow to its own validator.
    """
    src = _normalize_pasted(text or "")

    # ── config half: reuse the scored object picker, re-serialize to text ──
    config_text = ""
    config_span = None
    try:
        obj = _best_config_object(src)
    except Exception:  # noqa: BLE001 — splitter must never raise
        obj = None
    if isinstance(obj, dict):
        config_text = json.dumps(obj)
        # Locate the object's literal span in the source so seed-line scanning can
        # EXCLUDE it (a pipe inside preferences_md must not read as a seed line).
        config_span = _locate_object_span(src, obj)

    # ── seeds half: prefer the labeled fence, else pipe-shaped lines outside JSON ──
    seed_text = ""
    fence = _SEEDS_FENCE_RE.search(src)
    if fence is not None:
        body = fence.group(1)
        lines = [ln.rstrip() for ln in body.splitlines()
                 if _SEED_LINE_RE.match(ln)]
        seed_text = "\n".join(lines)
    if not seed_text:
        lo, hi = config_span if config_span is not None else (None, None)
        lines = []
        for m in re.finditer(r"^.*$", src, re.MULTILINE):
            if not _SEED_LINE_RE.match(m.group(0)):
                continue
            # Skip a pipe-line that falls inside the JSON object's span.
            if lo is not None and lo <= m.start() < hi:
                continue
            lines.append(m.group(0).rstrip())
        seed_text = "\n".join(lines)

    return config_text, seed_text


def _span_matches(candidate: str, obj: dict) -> bool:
    """True when the raw ``candidate`` substring parses to ``obj``, TOLERANTLY.

    ``_best_config_object`` may return an object that came from its trailing-comma
    /comment repair fallback (``claude_bridge._extract_json``), so the object is
    the REPAIRED dict while the source substring still carries the trailing comma.
    A strict ``json.loads(candidate) == obj`` therefore never matches on that path
    (JSONDecodeError on the comma) and the span can't be pinned — which used to let
    a ``preferences_md`` value like ``"portfolio | https://…"`` leak into seed_text.
    We mirror the same repair here (strip trailing commas, then retry) so the span
    is located on the tolerant path too, keeping the pipe-inside-JSON guard intact."""
    from claude_bridge import _strip_trailing_commas
    for cand in (candidate, _strip_trailing_commas(candidate)):
        try:
            if json.loads(cand) == obj:
                return True
        except (json.JSONDecodeError, ValueError):
            pass
    return False


def _locate_object_span(text: str, obj: dict) -> tuple[int, int] | None:
    """Return the ``[start, end)`` char span of the brace-balanced JSON object in
    ``text`` that parses to ``obj`` (the config block), or None if it can't be
    pinned. Used by ``split_full_reply`` to exclude the config block's interior
    (which may contain pipe characters) from seed-line scanning. Mirrors
    ``_best_config_object``'s brace-walk AND its trailing-comma tolerance (via
    ``_span_matches``) so the SAME object is located even on the repair fallback."""
    depth, start = 0, None
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}" and depth > 0:
            depth -= 1
            if depth == 0 and start is not None:
                if _span_matches(text[start:i + 1], obj):
                    return (start, i + 1)
                start = None
    return None


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
    from scrape.ats_detect import parse_line, probe_board, is_tos_blocked_host
    from scrape.company_registry import (UNVERIFIED_FLAG, is_browser_only,
                                         is_unverified, save_companies,
                                         get_registry)

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
    # short-circuit as skipped. BROWSER-ONLY stored boards (S33) likewise flow
    # through: a re-seed re-probes them, and if the wall came down the live
    # verdict reaches save_companies' upgrade and the board re-enters the
    # scraped set — short-circuiting them as "skipped" would strand a board on
    # extension-only refresh forever after its wall opened up (S33 review fix).
    try:
        _all = get_registry(include_unverified=True)
        known = {(c.name or "").lower() for c in _all
                 if not is_unverified(c) and not is_browser_only(c)}
        _browser_only_names = {(c.name or "").lower() for c in _all
                               if is_browser_only(c)}
    except Exception:
        known = set()
        _browser_only_names = set()

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
        # Verify: a board is 'live' (verified) only when the probe actually READ
        # it — a live board with 0 open jobs (reachable, count 0) verifies, but a
        # CSRF/Cloudflare-walled workday_cxs tenant (HTTP 422 -> unreachable) does
        # NOT: "verified" for a board the scraper can never read is a lie. It lands
        # in the same flagged-unverified bucket as any unreachable board (saved,
        # excluded from scraping, re-verify upgrade path applies if it opens up).
        pr = probe_board(e) if probe else None
        if pr is not None and pr.reachable:
            n = pr.count if pr.count is not None else 0
            verdicts.append({"name": e.name, "ats_type": e.ats_type,
                             "slug": e.slug, "verdict": "live", "count": n,
                             "detail": f"live ({n} open jobs)"})
            to_save.append(e)
        elif (e.name or "").lower() in _browser_only_names:
            # Stored browser-only and STILL walled: nothing to save (an incoming
            # unverified entry never overwrites the stored record, and demoting
            # confirmed-real to unverified would be strictly worse). Report the
            # honest state instead of a misleading "saved unverified".
            verdicts.append({"name": e.name, "ats_type": e.ats_type,
                             "slug": e.slug, "verdict": "unreachable",
                             "detail": "still walled — kept browser-only "
                                       "(browse it with the extension to "
                                       "refresh)"})
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
