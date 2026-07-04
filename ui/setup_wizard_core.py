"""Tk-free core of the first-run Setup wizard.

Everything the wizard's on-disk CONTRACT needs — the answers→preferences
transform, the search-config seed, the résumé auto-structurer, salary parsing,
the field presets / career-level mapping, the onboarding marker, and the
existing-config prefill — lives here so the web onboarding API and the AI-setup
path can reuse the EXACT wizard contract without importing tkinter (importing
tkinter server-side is pointless and can fail on a headless box). ``ui/
setup_wizard.py`` re-exports every public name from this module and adds only the
Tk ``SetupWizard`` window on top, so existing callers/tests that reach
``setup_wizard.build_preferences`` / ``setup_wizard.parse_salary_input`` /
``setup_wizard.mark_onboarded`` (etc.) keep working byte-for-byte.

The AI-assisted path (``ui/ai_setup.py``) and the wizard MUST converge on the
same on-disk shape: both funnel through ``build_preferences`` + ``_search_config``
+ ``workspace.scaffold_preferences`` / ``workspace.save_config`` here.

Design constraints (repo rules): no display dependency, pure/side-effect-scoped
transforms, never raises for ordinary bad input (returns None / '' / unchanged).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import config
import workspace

_MARKER_NAME = ".onboarded"


# -- resume auto-structuring (P0 #1) ---------------------------------------------
# The wizard invites a PLAIN-TEXT resume paste, but resume/experience_parser
# raises on any resume without '## ' markdown headings -- so a pasted nurse/welder/
# teacher resume crashed every subsequent search. structure_resume_text() turns
# a raw paste into a headed document the parser accepts, WITHOUT losing any text:
#   - already has '## '/'# ' headings  -> returned unchanged.
#   - has recognizable ALL-CAPS / alias heading lines (EXPERIENCE, EDUCATION,
#     LICENSES, SKILLS, ...) -> those lines are promoted to '## ' headings.
#   - otherwise -> leading contact-looking lines go under '## CONTACT' and the
#     rest under '## WORK EXPERIENCE'.
# Pure and side-effect-free so it is trivially unit-testable.

# Lines that look like contact info (email / phone / a short name or address at
# the very top), grouped under CONTACT when we have to wrap a bare paste.
_EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
_PHONE_RE = re.compile(r"(?:\+?\d[\d\-\.\s()]{7,}\d)")


# -- salary input parsing (P3 hourly-wage support) -------------------------------
# Annual-equivalent of a full-time hourly wage (40 h/wk x 52 wk). Matches
# match.scorer's 2080 annualization so a wizard-entered "18/hr" floor and a
# description-parsed hourly rate line up.
_FULLTIME_HOURS_PER_YEAR = 2080
_HOURLY_INPUT_RE = re.compile(r"/\s*h|\bhr\b|\bhour", re.I)


def _derive_industry(industry: str, roles: list) -> str:
    """When the optional industry box is blank, resolve the user's roles to an
    O*NET-SOC occupation and return a short field label IFF it lands on a
    NON-engineering occupation. Returns '' (keep today's behavior byte-identical)
    when the industry is already set, no role resolves, or the resolved role is
    engineering/tech-like. The first role that confidently resolves wins."""
    if (industry or "").strip():
        return ""
    try:
        import industry_profile
    except Exception:
        return ""
    for role in roles:
        role = (role or "").strip()
        if not role:
            continue
        try:
            soc = industry_profile.resolve_soc(role)  # None for eng-like/unresolved
        except Exception:
            soc = None
        if soc and soc.get("title"):
            return str(soc["title"]).strip()
    return ""


def parse_salary_input(text: str) -> int | None:
    """Parse a free-text salary floor into ANNUAL dollars, accepting both annual
    ('90000', '$90,000', '90k') and hourly ('18/hr', '$18.50 per hour', '25 hr')
    inputs. Hourly values are annualized at 2080 h/yr. Returns None for blank or
    unparseable input (never raises)."""
    s = (text or "").strip().lower()
    if not s:
        return None
    hourly = bool(_HOURLY_INPUT_RE.search(s))
    # Pull the first numeric token (allow a decimal point and 'k' suffix).
    m = re.search(r"(\d[\d,]*\.?\d*)\s*(k)?", s)
    if not m:
        return None
    num = m.group(1).replace(",", "")
    try:
        val = float(num)
    except ValueError:
        return None
    if m.group(2):            # explicit 'k' suffix -> thousands
        val *= 1000
    if hourly:
        val *= _FULLTIME_HOURS_PER_YEAR
    # A small bare number with no 'k' and no hourly marker (e.g. "18") is almost
    # certainly an hourly wage a user typed without the unit; annualize it so it
    # isn't stored as an $18 floor. 1000 is the cutoff (nobody means $18/yr).
    elif val < 1000:
        val *= _FULLTIME_HOURS_PER_YEAR
    val = int(round(val))
    return val if val > 0 else None


def _alias_table() -> dict:
    """The parser's normalized-heading -> canonical-heading map, reused so the
    wizard promotes exactly the headings the parser will recognize."""
    from resume.experience_parser import _HEADING_ALIASES, EXPERIENCE_SECTIONS
    table = dict(_HEADING_ALIASES)
    # The canonical names themselves are valid headings too.
    for canon in EXPERIENCE_SECTIONS.values():
        table.setdefault(canon, canon)
    return table


def _normalize_heading_line(line: str) -> str:
    return re.sub(r"\s+", " ", line.strip().upper()).rstrip(":").strip()


def _looks_like_heading(line: str, table: dict) -> str | None:
    """Return the canonical heading a bare line maps to, or None. A line is a
    heading candidate only if it is short and has no sentence punctuation (so a
    real experience sentence that happens to contain a keyword isn't promoted)."""
    raw = line.strip()
    if not raw or len(raw) > 40:
        return None
    if any(ch in raw for ch in ".!?,;:") and not raw.rstrip().endswith(":"):
        return None
    norm = _normalize_heading_line(raw)
    return table.get(norm)


def _looks_like_contact(line: str) -> bool:
    return bool(_EMAIL_RE.search(line) or _PHONE_RE.search(line))


# A bare "Experience"-family line. The parser DELIBERATELY does not alias a bare
# "EXPERIENCE" to WORK EXPERIENCE (it is commonly a document H1 title that would
# shadow the real '## WORK EXPERIENCE' section — see experience_parser
# _HEADING_ALIASES). But when we are folding ORPHAN lines that sit BEFORE the first
# recognized heading (Path A), such a line is unambiguously a section label, not
# the doc title, so it is safe to treat it as the WORK EXPERIENCE heading here.
_BARE_EXPERIENCE_RE = re.compile(r"^\s*(work\s+)?experiences?\s*:?\s*$", re.I)


def _is_bare_experience(line: str) -> bool:
    return bool(_BARE_EXPERIENCE_RE.match(line or ""))


def structure_resume_text(text: str) -> tuple[str, bool]:
    """Return (structured_markdown, was_restructured).

    was_restructured is True only when we actually inserted headings, so the
    wizard can show a gentle notice. Never raises; never drops text."""
    raw = (text or "").strip()
    if not raw:
        return raw, False
    # Already structured (any markdown H1/H2) -> leave it be.
    if re.search(r"(?m)^#{1,2}\s+\S", raw):
        return raw, False

    table = _alias_table()
    lines = raw.splitlines()

    # Path A: promote recognizable ALL-CAPS/alias heading lines in place.
    promoted: list[str] = []
    n_headings = 0
    first_heading_idx: int | None = None
    for i, line in enumerate(lines):
        canon = _looks_like_heading(line, table)
        if canon is not None:
            if first_heading_idx is None:
                first_heading_idx = i
            promoted.append(f"## {canon}")
            n_headings += 1
        else:
            promoted.append(line)
    if n_headings:
        # Any non-blank line BEFORE the first recognized heading is "orphan" text
        # the downstream parser can't see (it lives under no section, so
        # load_experience drops it — that silently deleted a whole résumé whose
        # work history sat under a bare "Experience" line the parser deliberately
        # won't alias). Rather than drop it, fold the orphan block into
        # CONTACT/WORK EXPERIENCE sections exactly like Path B does, so no pasted
        # text is ever invisible. (scenario-test finding #1)
        assert first_heading_idx is not None
        orphans = lines[:first_heading_idx]
        rest = promoted[first_heading_idx:]
        if any(o.strip() for o in orphans):
            folded = _wrap_orphan_block(orphans)
            head = (folded + [""]) if folded else []
            return "\n".join(head + rest).strip(), True
        return "\n".join(promoted).strip(), True

    # Path B: no recognizable headings at all -- wrap. Leading contact-looking
    # lines (name/email/phone/address at the top) go under CONTACT; the body
    # under WORK EXPERIENCE so the parser + scorer both have real content.
    folded = _wrap_orphan_block(lines)
    return "\n".join(folded).strip() if folded else raw, True


def _wrap_orphan_block(lines: list[str]) -> list[str]:
    """Wrap unheaded résumé lines into ``## CONTACT`` / ``## WORK EXPERIENCE``
    sections so the parser + scorer see real content instead of dropping it.

    Leading contact-looking lines (name/email/phone/address at the very top) go
    under CONTACT; everything after goes under WORK EXPERIENCE. A bare
    "Experience"/"Work Experience" label inside the block is consumed as the
    section header itself (it is unambiguously a label here, not a doc title).
    Returns the wrapped lines (no trailing/leading blank trimming — the caller
    joins + strips)."""
    contact: list[str] = []
    body_start = 0
    for i, line in enumerate(lines[:6]):  # only scan the top of the document
        if not line.strip():
            body_start = i + 1
            continue
        if _looks_like_contact(line) or (i == 0 and len(line.strip()) <= 60):
            contact.append(line.strip())
            body_start = i + 1
        else:
            break
    body_lines = lines[body_start:]
    # Drop a leading bare "Experience" label — the "## WORK EXPERIENCE" heading we
    # emit below replaces it (so it isn't repeated as literal body text).
    while body_lines and not body_lines[0].strip():
        body_lines = body_lines[1:]
    if body_lines and _is_bare_experience(body_lines[0]):
        body_lines = body_lines[1:]
    body = "\n".join(body_lines).strip()
    out: list[str] = []
    if contact:
        out.append("## CONTACT")
        out.append("")
        out.extend(f"- {c}" for c in contact)
        out.append("")
    out.append("## WORK EXPERIENCE")
    out.append("")
    out.append(body if body else "\n".join(lines).strip())
    return out


# ── connected-source detection (keys step) ──────────────────────────────────────
# Impact-ranked (Adzuna first, CareerOneStop second, then the rest) so the wizard
# keys step and its "Connected:" hint agree with the persona-measured coverage
# order. Each entry: (display label, list of required secret names). A source is
# "connected" only when EVERY one of its credentials resolves (env-then-secret),
# via the same config.resolve_secret path the source clients use.
_KEYED_SOURCES = [
    ("Adzuna", ["adzuna_app_id", "adzuna_app_key"]),
    ("CareerOneStop", ["careeronestop_user_id", "careeronestop_token"]),
    ("Jooble", ["jooble_api_key"]),
    ("Careerjet", ["careerjet_affid"]),
    ("USAJobs", ["usajobs_api_key", "usajobs_email"]),
]


def _credential_present(secret_name: str) -> bool:
    """True when a single credential resolves (env-then-secret), mirroring how the
    source clients read it. usajobs_email accepts the client's USAJOBS_USER_AGENT
    fallback so the hint matches the client's real resolution."""
    import os
    if secret_name == "usajobs_email":
        return bool(os.getenv("USAJOBS_EMAIL") or os.getenv("USAJOBS_USER_AGENT")
                    or config.read_secret("usajobs_email"))
    return bool(config.resolve_secret(secret_name.upper(), secret_name))


def connected_source_labels() -> list[str]:
    """Return the display labels of keyed sources whose credentials are all
    present, impact-ranked. Pure-ish (reads only credential state); never raises.
    Used by the wizard keys step to show progress without a live probe."""
    out: list[str] = []
    for label, secrets in _KEYED_SOURCES:
        try:
            ok = all(_credential_present(name) for name in secrets)
        except Exception:
            ok = False
        if ok:
            out.append(label)
    return out


# ── onboarding marker (PER-PROJECT) ─────────────────────────────────────────────
# The wizard-completion marker is scoped to the PROJECT's data dir, not a single
# installation-wide root file. A global marker made every project after the first
# report onboarded:true even though it was never wizard-configured (its resume/
# about/salary/industry all blank) — so the wizard never offered to set them up.
# For the root/'default' slug, workspace.project_dir() returns USER_DATA_DIR, so
# the marker path is byte-identical to the legacy location: an existing single-
# project install's root .onboarded keeps marking the default project onboarded
# (automatic migration, no move needed). (scenario finding #5)
def _marker_path(slug: str | None = None) -> Path:
    try:
        base = workspace.project_dir(slug)
    except Exception:
        base = Path(config.USER_DATA_DIR)
    return Path(base) / _MARKER_NAME


def is_onboarded(slug: str | None = None) -> bool:
    """True when THIS project (the active one, or the named slug) has completed the
    wizard. Migration: for the root/'default' project the path resolves to the
    legacy root marker, so a pre-migration install stays onboarded.

    Legacy-config inference (S36b): projects configured BEFORE the per-project
    marker existed have a complete config but no marker, which re-gated them
    behind the wizard on every web load. A config that already carries the
    wizard's core output (non-empty ``keywords``) counts as onboarded. Pure
    READ — no marker is written here (GET /api/onboarding calls this; a read
    route must not mutate state, and ``ai_setup.apply_setup(mark_onboarded=
    False)`` relies on the marker staying absent until the wizard finishes)."""
    if _marker_path(slug).exists():
        return True
    try:
        cfg = workspace.load_config(slug)
    except Exception:
        return False
    return bool(cfg.get("keywords"))


def mark_onboarded(slug: str | None = None) -> None:
    p = _marker_path(slug)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("ok\n", encoding="utf-8")
    except OSError:
        pass


# ── pure transform: answers -> on-disk preferences contract ─────────────────────
def build_preferences(answers: dict) -> dict:
    """Map wizard answers into {"hard": dict, "profile_md": str}. Pure (no I/O)
    so it is easy to test. Mirrors the shape preferences.load() expects.

    answers keys: roles (list[str]), location (str), remote_ok (bool),
    salary_min (int|None), about (str)."""
    roles = [r.strip() for r in answers.get("roles", []) if r and r.strip()]
    location = (answers.get("location") or "").strip()
    remote_ok = bool(answers.get("remote_ok", True))
    salary_min = answers.get("salary_min")
    about = (answers.get("about") or "").strip()

    hard = {
        "salary_min": salary_min if salary_min else None,
        "locations": [location] if location else [],
        "remote_ok": remote_ok,
        "work_auth": "",
        "dealbreakers": [],
        "seniority_exclude": [],
        "target_roles": list(roles),
    }

    lines = [
        "# My Job Preferences",
        "",
        "> Describe the roles you want in plain English. The AI reads this to rank",
        "> and sort jobs to your taste. Be specific about what you love and avoid.",
        "",
    ]
    if roles:
        lines += ["Target roles / keywords I care about: " + ", ".join(roles), ""]
    if location:
        where = location + (" (remote is fine too)" if remote_ok else "")
        lines += [f"Where I want to work: {where}", ""]
    if salary_min:
        lines += [f"Minimum salary I'll consider: ${salary_min:,}", ""]
    if about:
        lines += ["## About me / what I'm looking for", "", about, ""]
    return {"hard": hard, "profile_md": "\n".join(lines)}


def prefill_from_existing(prefs: dict | None = None, cfg: dict | None = None) -> dict:
    """Return {roles, location, remote_ok, salary_min, about} loaded from the
    current preferences + search config for wizard pre-population.  Pure: when
    prefs and cfg are supplied no I/O happens, making this easy to unit-test.
    Reads from disk when either argument is None."""
    if prefs is None:
        try:
            import preferences as _prefs_mod
            prefs = _prefs_mod.load()
        except Exception:
            prefs = {}
    if cfg is None:
        try:
            cfg = workspace.load_config()
        except Exception:
            cfg = {}
    hard = (prefs or {}).get("hard", {})

    # Roles: prefer hard.target_roles, fall back to cfg.keywords
    roles_list = hard.get("target_roles") or cfg.get("keywords") or []
    roles_str = ", ".join(roles_list)

    # Location: prefer hard.locations[0], fall back to cfg.location
    locations = hard.get("locations") or []
    location = (locations[0] if locations else None) or cfg.get("location") or ""

    remote_ok = bool(hard.get("remote_ok", True))

    salary_min = hard.get("salary_min")

    # About: extract the section after "## About me" in the profile_md
    md = (prefs or {}).get("profile_md", "")
    about = ""
    _marker = "## About me / what I'm looking for"
    if _marker in md:
        about = md.split(_marker, 1)[1].strip()

    return {
        "roles": roles_str,
        "location": str(location),
        "remote_ok": remote_ok,
        "salary_min": str(salary_min) if salary_min else "",
        "about": about,
        "industry": str(cfg.get("industry") or ""),
        "level": _config_to_level(cfg or {}),
    }


# ── field presets (QW-1 / §6.2) ──────────────────────────────────────────────
# The free-text industry box silently mis-routed: a multi-word field ("mechanical
# engineering", "data analytics") tripped the P0-1 registry-tag bug and health
# synonym pollution. A validated preset picker fixes this AT THE SOURCE — each
# preset emits a CANONICAL industry token that (a) resolves to a non-generic
# industry_profile (source != 'generic', so Muse/Jobicy routing + query synonyms
# turn on) AND (b) matches the token-aware registry matcher for its own seeds.
#
# Every token here is a regression-tested contract (tests/ui/test_field_presets.py):
# each must resolve to a non-generic profile and self-match under the registry's
# _industry_tag_match. The tokens span the eight tested personas + the eng fields
# Alex uses. The last entry is an "Other" escape hatch that keeps the free-text
# box for anything unlisted (reach is never reduced — an unlisted field still
# searches broadly via the generic fallback).
_OTHER_PRESET = "Other (type your own)…"
_FIELD_PRESETS: list[tuple[str, str]] = [
    # (display label shown in the dropdown, canonical industry token emitted)
    ("Software engineering", "software engineering"),
    ("Mechanical engineering", "mechanical engineering"),
    ("Controls / automation engineering", "controls engineering"),
    ("Data analytics / data science", "data analytics"),
    ("Consulting", "consulting"),
    ("Marketing", "marketing"),
    ("Warehouse / logistics", "warehouse logistics"),
    ("Teaching / education (K-12)", "education"),
    ("Nursing / healthcare", "nursing"),
    ("Finance / accounting", "finance"),
    (_OTHER_PRESET, ""),
]
# display label -> canonical token, and the reverse (token -> label) for prefill.
_PRESET_TO_TOKEN: dict[str, str] = {label: tok for label, tok in _FIELD_PRESETS}
_PRESET_LABELS: list[str] = [label for label, _ in _FIELD_PRESETS]


def preset_tokens() -> list[str]:
    """The canonical industry tokens every non-'Other' preset emits (for tests
    and any caller that wants to enumerate the validated fields)."""
    return [tok for _label, tok in _FIELD_PRESETS if tok]


def _token_to_preset_label(industry: str) -> str:
    """The dropdown label whose canonical token matches `industry` (case/space-
    insensitive), or the 'Other' label when it's a custom/unlisted field. Blank
    industry -> '' (nothing selected). Used to pre-select the picker when the
    wizard reopens on an already-configured field."""
    ind = (industry or "").strip().lower()
    if not ind:
        return ""
    for label, tok in _FIELD_PRESETS:
        if tok and tok.lower() == ind:
            return label
    return _OTHER_PRESET


# Career-level → rubric config (match.rubric reads these off the search config).
# Only emitted when a level is chosen, so an unset level leaves defaults intact.
_LEVELS = ("", "Entry", "Mid", "Senior", "Manager/Exec")


def _level_to_config(level: str) -> dict:
    lvl = (level or "").strip().lower()
    if lvl in ("entry", "entry-level", "junior"):
        return {"seniority_target": "entry", "allow_intern": True, "years_cap": 3}
    if lvl in ("mid", "mid-level"):
        return {"seniority_target": "mid", "years_cap": 8}
    if lvl == "senior":
        return {"seniority_target": "senior", "years_cap": 12}
    if lvl in ("manager/exec", "manager", "exec", "executive", "management"):
        return {"seniority_target": "senior-exec", "allow_management": True, "years_cap": 25}
    return {}


def _config_to_level(cfg: dict) -> str:
    if cfg.get("allow_management"):
        return "Manager/Exec"
    return {"entry": "Entry", "mid": "Mid", "senior": "Senior",
            "senior-exec": "Manager/Exec"}.get(
        (cfg.get("seniority_target") or "").lower(), "")


def _search_config(answers: dict, existing: dict | None = None) -> dict:
    """Seed the search-tab config (keywords/location/salary/industry/level) from
    answers so the Search tab pre-fills. Preserves any existing keys."""
    cfg = dict(existing or {})
    roles = [r.strip() for r in answers.get("roles", []) if r and r.strip()]
    if roles:
        cfg["keywords"] = roles
    if (answers.get("location") or "").strip():
        cfg["location"] = answers["location"].strip()
    if answers.get("salary_min"):
        cfg["salary_min"] = answers["salary_min"]
    if (answers.get("industry") or "").strip():
        cfg["industry"] = answers["industry"].strip()
    if (answers.get("level") or "").strip():
        cfg.update(_level_to_config(answers["level"]))  # rubric-read keys
    return cfg


def apply(answers: dict) -> dict:
    """Write the preferences contract, the search config, and (if the user
    supplied resume text) experience.md, then mark onboarding complete.

    Returns a small info dict {"resume_restructured": bool} so the caller can
    show a gentle notice when a plain-text paste had to be auto-structured. A
    pasted resume is ALWAYS run through structure_resume_text() first so it can
    never crash later scoring/generation (P0 #1)."""
    prefs = build_preferences(answers)
    # Write the contract through the shared scaffold helper (the same one
    # create_project + the AI-assisted-setup path use) so all three paths agree
    # on the preferences shape. Supplying hard/profile_md overwrites both files.
    workspace.scaffold_preferences(hard=prefs["hard"],
                                   profile_md=prefs["profile_md"])

    workspace.save_config(_search_config(answers, workspace.load_config()))

    info = {"resume_restructured": False}
    resume = (answers.get("resume_text") or "").strip()
    if resume:
        structured, restructured = structure_resume_text(resume)
        info["resume_restructured"] = restructured
        exp = workspace.experience_file()
        exp.parent.mkdir(parents=True, exist_ok=True)
        exp.write_text(structured, encoding="utf-8")

    mark_onboarded()
    return info
