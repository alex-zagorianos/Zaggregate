"""Deterministic job-fact extraction — the 'extract' stage of the AI-ranking
pipeline (brain/spec-2026-06-29-ai-pipeline-optimization.md §5 Task A).

Pulls a small, structured fact set out of a messy job posting using regex +
keyword heuristics, so the downstream gate (match/gate) can filter and the
compact AI request (ranker.build_compact_request) can score from ~40 tokens of
facts instead of 1500 chars of HTML. No model tokens, cached by job_key.

When the deferred local-model work lands, the model only fills the handful of
fields heuristics get wrong — the contract (the JobFacts dict) stays the same.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from match.scorer import salary_from_text, _term_pattern

# ── seniority ────────────────────────────────────────────────────────────────
# Checked in priority order against the TITLE first, then the description.
_SENIORITY = [
    ("intern",   re.compile(r"\bintern(ship)?\b|\bco-?op\b", re.I)),
    ("director", re.compile(r"\bdirector\b|\bhead of\b|\bvp\b|vice president|\bchief\b", re.I)),
    ("manager",  re.compile(r"\bmanager\b|\bmgr\b", re.I)),
    ("lead",     re.compile(r"\blead\b|\bprincipal\b|\bstaff\b", re.I)),
    ("senior",   re.compile(r"\bsenior\b|\bsr\.?\b", re.I)),
    ("entry",    re.compile(r"\bentry[- ]?level\b|\bjunior\b|\bjr\.?\b|\bassociate\b|new ?grad|\blevel\s*1\b|\bl1\b", re.I)),
]
# Roman-numeral job level in a title: "Engineer I/II/III".
_ROMAN = re.compile(r"(?:^|\s|-)\s*(I{1,3})\s*(?:$|\s|-|,)")
_ROMAN_MAP = {"I": "entry", "II": "mid", "III": "senior"}

# A number of years counts as a REQUIREMENT only when an experience qualifier is
# nearby; "over 25 years in business / serving / founded" is company tenure, not
# a requirement, and must NOT gate the job.
_YEARS_EXP = re.compile(
    r"(\d{1,2})\s*\+?\s*(?:years|yrs)(?=[^.\n]{0,30}?\b(?:experience|exp|background)\b)"
    r"|\b(?:experience|exp|minimum|at least|min\.?)\b[^.\n]{0,30}?(\d{1,2})\s*\+?\s*(?:years|yrs)",
    re.I)

_CLEARANCE = re.compile(
    r"security clearance|ts/sci|top secret|secret clearance|active clearance|"
    r"polygraph|\bdod\b\s+clearance|clearance (?:is\s+)?required|must (?:have|possess) "
    r"(?:an?\s+)?(?:active\s+)?clearance", re.I)

# A negator near a clearance mention means the job does NOT require one
# ("No security clearance required", "ability to obtain a clearance").
_CLEARANCE_NEG = re.compile(
    r"\b(?:no|not|without|don't|do not|does not|do not require|does not require|"
    r"not require[ds]?|ability to obtain|able to obtain|eligible to obtain|"
    r"willing to obtain|will (?:help )?(?:you )?obtain)\b", re.I)


def _detect_clearance(text: str) -> bool:
    """True only if a clearance is AFFIRMATIVELY required. A negator within ~40
    chars (before or after) of a clearance mention suppresses it."""
    for m in _CLEARANCE.finditer(text):
        window = text[max(0, m.start() - 40): m.end() + 40]
        if not _CLEARANCE_NEG.search(window):
            return True
    return False

# ── work-authorization / location restrictions ───────────────────────────────
_RESTRICTIONS = [
    ("Japan work visa required",   re.compile(r"japanese work visa|valid japanese|located in japan", re.I)),
    ("EU/UK work authorization required", re.compile(r"\beu work|located in (?:europe|the eu)|uk work visa|united kingdom work", re.I)),
    ("Non-US location required",   re.compile(r"must (?:be )?(?:located|reside) in (?!the united states|the us\b)(?:canada|australia|india|germany|mexico|brazil)", re.I)),
    ("No visa sponsorship (US work auth required)", re.compile(r"unable to (?:offer|provide|sponsor)[^.]{0,30}(?:visa|sponsorship)|no visa sponsorship|without sponsorship|not (?:able|eligible) to sponsor", re.I)),
    ("US work authorization required", re.compile(r"must be authorized to work in the united states|\bu\.?s\.? person\b|u\.?s\.? citizen", re.I)),
]

# ── role archetype (title weighted ×3) ───────────────────────────────────────
_ROLE_KEYWORDS = {
    "manage":   ["people management", "manage a team", "manage the team", "direct reports",
                 "engineering manager", "director of", "head of", "lead and grow", "build and lead the team"],
    "sales":    ["sales", "account executive", "quota", "pre-sales", "presales",
                 "solutions engineer", "solution engineer", "customer success", "business development"],
    "test":     ["sdet", "test engineer", "qa engineer", "quality assurance", "validation",
                 "test automation", "hardware-in-the-loop", "hardware in the loop", "developer engineer in test"],
    "maintain": ["maintenance", "sustaining", "field service", "support engineer",
                 "on-call support", "sustainment"],
    "research": ["research scientist", "research engineer", "r&d ", "analysis engineer",
                 "applied research", "investigate novel"],
    "integrate":["integration engineer", "systems integration", "bring-up", "bring up",
                 "commissioning", "deployment engineer"],
    "build":    ["design", "develop", "build", "implement", "architect", "create",
                 "firmware", "prototype", "new product", "control system"],
}

_SKILL_VOCAB = [
    "c++", "c#", ".net", "python", "embedded", "firmware", "stm32", "rtos", "freertos",
    "plc", "scada", "motion control", "servo", "real-time", "ros2", "ros", "can bus",
    "ethercat", "labview", "fpga", "verilog", "vhdl", "matlab", "simulink", "gd&t",
    "solidworks", "creo", "fea", "hardware-in-the-loop", "hil", "linux", "control systems",
    "kinematics", "pcb", "kicad", "machine vision", "opencv", "sensor fusion", "gnc",
    "controls", "automation", "robotics", "mechatronics", "hmi", "cnc", "i2c", "uart",
]

# Universal role buckets merged in ONLY for non-tech fields (agnostic, plan 1E).
# Additive: none of these keywords fire on an engineering title/description, so a
# tech posting's role_type is unchanged — but they let a nurse/clerk/accountant
# posting classify correctly instead of defaulting to "build".
_UNIVERSAL_ROLE_KEYWORDS = {
    "care":    ["nurse", "rn ", "registered nurse", "clinical", "patient care",
                "caregiver", "therapist", "physician", "medical assistant", "bedside",
                "informatics"],
    "admin":   ["administrative", "office manager", "receptionist", "scheduler",
                "clerk", "data entry", "front desk", "administrative assistant"],
    "finance": ["accountant", "accounting", "financial analyst", "bookkeeper",
                "auditor", "payroll", "accounts payable", "accounts receivable"],
    "trade":   ["electrician", "plumber", "hvac technician", "welder", "carpenter",
                "machinist", "install technician", "maintenance technician"],
}

# Industry tokens that keep the engineering-tuned maps (byte-identical for Alex).
_TECH_TOKENS = {
    "controls", "control", "engineering", "engineer", "software", "robotics",
    "embedded", "mechanical", "mechatronics", "automation", "hardware", "electrical",
    "manufacturing", "industrial", "aerospace", "ai", "ml", "data", "tech",
    "technology", "semiconductor", "firmware",
}


def is_tech_industry(industry: str) -> bool:
    """True when the engineering-tuned role map / skill vocab fits this field (or
    it's empty). Non-tech fields merge the universal buckets + use profile skills."""
    toks = [t for t in re.split(r"[\s_\-/,]+", (industry or "").lower()) if t]
    return not toks or any(t in _TECH_TOKENS for t in toks)


def _role_keywords_for(industry: str) -> dict:
    """The engineering map for tech/empty industries (byte-identical); the eng map
    PLUS universal buckets for any other field."""
    if is_tech_industry(industry):
        return _ROLE_KEYWORDS
    return {**_ROLE_KEYWORDS, **_UNIVERSAL_ROLE_KEYWORDS}


def _detect_seniority(title: str, desc: str) -> str:
    for level, pat in _SENIORITY:
        if pat.search(title):
            return level
    m = _ROMAN.search(title)
    if m:
        return _ROMAN_MAP[m.group(1).upper()]
    for level, pat in _SENIORITY:
        if pat.search(desc):
            return level
    return "mid"


def _detect_required_years(text: str) -> Optional[int]:
    yrs = []
    for m in _YEARS_EXP.finditer(text):
        g = m.group(1) or m.group(2)
        if g and int(g) <= 30:
            yrs.append(int(g))
    return max(yrs) if yrs else None


def _detect_location_type(location: str, desc_head: str) -> str:
    blob = f"{location} {desc_head}".lower()
    if "hybrid" in blob:
        return "hybrid"
    if "remote" in blob:
        return "remote"
    if (location or "").strip():
        return "onsite"
    return "unknown"


def _detect_restriction(text: str) -> Optional[str]:
    for label, pat in _RESTRICTIONS:
        if pat.search(text):
            return label
    return None


def _detect_role_type(title: str, desc: str, role_map: dict | None = None) -> str:
    role_map = role_map or _ROLE_KEYWORDS
    tl, dl = title.lower(), desc.lower()
    scores = {role: 0 for role in role_map}
    for role, kws in role_map.items():
        for kw in kws:
            if kw in tl:
                scores[role] += 3
            elif kw in dl:
                scores[role] += 1
    best = max(scores, key=lambda r: scores[r])
    return best if scores[best] > 0 else "build"


def _detect_skills(desc: str, limit: int = 6, terms=None) -> list[str]:
    dl = (desc or "").lower()
    vocab = terms if terms else _SKILL_VOCAB
    hits = []
    for term in vocab:
        if term and _term_pattern(term).search(dl):
            hits.append(term)
        if len(hits) >= limit:
            break
    return hits


def extract_facts(job, *, skill_terms=None, industry: str = "") -> dict:
    """Pure deterministic extraction of structured facts from a JobResult.

    Returns a JobFacts dict:
      {seniority, required_years, role_type, clearance_required, location_type,
       restriction, comp_min, comp_max, top_skills}

    `industry`/`skill_terms` are agnostic seams (plan 1E): a non-tech industry
    merges universal role buckets; `skill_terms` (profile-derived) replaces the
    engineering skill vocab. Defaults ('' / None) reproduce the original output
    byte-for-byte, so an engineering seeker is unaffected.
    """
    title = job.title or ""
    desc = job.description or ""
    text = f"{title}\n{desc}"

    comp_min, comp_max = job.salary_min, job.salary_max
    if comp_min is None and comp_max is None and desc:
        comp_min, comp_max = salary_from_text(desc)

    seniority = _detect_seniority(title, desc)
    role_type = _detect_role_type(title, desc, _role_keywords_for(industry))
    # A manager/director title IS people-management for the gate's purposes, even
    # when generic "build" keywords dominate the body.
    if seniority in ("manager", "director"):
        role_type = "manage"

    return {
        "seniority": seniority,
        "required_years": _detect_required_years(text),
        "role_type": role_type,
        "clearance_required": _detect_clearance(text),
        "location_type": _detect_location_type(job.location or "", desc[:600]),
        "restriction": _detect_restriction(text),
        "comp_min": int(comp_min) if comp_min else None,
        "comp_max": int(comp_max) if comp_max else None,
        "top_skills": _detect_skills(desc, terms=skill_terms),
    }


def facts_summary(facts: dict) -> str:
    """A compact one-line fact block for the AI prompt (~30-40 tokens vs a
    1500-char description)."""
    sen = facts["seniority"]
    yrs = facts.get("required_years")
    sen_str = f"{sen} ({yrs}+ yrs req)" if yrs else sen
    comp = ""
    lo, hi = facts.get("comp_min"), facts.get("comp_max")
    if lo and hi:
        comp = f" | Comp: ${lo//1000}k-${hi//1000}k"
    elif lo:
        comp = f" | Comp: ${lo//1000}k+"
    skills = ", ".join(facts.get("top_skills") or []) or "n/a"
    parts = [
        f"Seniority: {sen_str}",
        f"Role: {facts['role_type']}",
        f"Location: {facts['location_type']}",
        f"Skills: {skills}",
        f"Clearance: {'yes' if facts['clearance_required'] else 'no'}",
    ]
    line = " | ".join(parts) + comp
    if facts.get("restriction"):
        line += f" | Restriction: {facts['restriction']}"
    return line


# ── cache seam (immutable per posting; ready for a model-backed extractor) ────
def _cache_dir() -> Path:
    from config import CACHE_DIR
    d = CACHE_DIR / "extracted"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _profile_sig(industry: str, skill_terms) -> str | None:
    """A short cache-key suffix when facts depend on a profile/field, so a health
    seeker's facts can't be served from an engineering seeker's cache (the trap:
    the cache is keyed by job_key only). None for the default tech/no-skills path
    -> the original `{job_key}.json` filename, byte-identical for Alex."""
    if is_tech_industry(industry) and not skill_terms:
        return None
    import hashlib
    payload = f"{(industry or '').lower()}|{','.join(sorted(skill_terms or []))}"
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:8]


def facts_for(job, *, use_cache: bool = True, skill_terms=None, industry: str = "") -> dict:
    """Cached extraction keyed by job_key (+ a profile signature when facts depend
    on the active field/profile, so they never leak across people/projects).
    Deterministic today; the cache is what makes a future model-backed extractor
    near-free on re-runs — only net-new postings are ever extracted."""
    if not use_cache:
        return extract_facts(job, skill_terms=skill_terms, industry=industry)
    from scrape.cache_helpers import read_cache, write_cache
    try:
        key = job.job_key
    except Exception:
        return extract_facts(job, skill_terms=skill_terms, industry=industry)
    sig = _profile_sig(industry, skill_terms)
    fname = f"{key}.json" if sig is None else f"{key}.{sig}.json"
    path = _cache_dir() / fname
    cached = read_cache(path)
    if isinstance(cached, dict) and "seniority" in cached:
        return cached
    facts = extract_facts(job, skill_terms=skill_terms, industry=industry)
    try:
        write_cache(path, facts)
    except OSError:
        pass
    return facts
