"""Derive BROAD, high-recall query keywords from a user's target-role list.

Why this exists (measured 2026-07-01): job-search APIs (Adzuna/USAJobs/JSearch/…)
phrase-match the keyword, so a narrow seniority-laden title like
"VP Clinical Informatics" or "Chief Medical Information Officer" returns ~0 hits,
while the FIELD term it contains ("clinical informatics") returns 20x more. The
right split is: query on broad field terms for RECALL, then let match/scorer.py +
match/gate.py handle seniority/exec-fit for PRECISION. This module produces the
query set; the original roles stay the scoring/target_roles set untouched.

Design guarantees:
- A plain IC title with no seniority tokens ("controls engineer") is returned
  unchanged, so Alex's engineering flow is byte-identical.
- Pure transform, no I/O — trivially testable and safe to call per search.
"""
from __future__ import annotations

import re
from typing import Iterable, Optional

# Whole-word tokens that denote SENIORITY/level or org-scope rather than the field
# of work. Stripped anywhere in a title so "Clinical Informatics Manager" and
# "Director Clinical Informatics" both collapse to "clinical informatics".
SENIORITY_TOKENS = frozenset({
    # exec / VP
    "vp", "svp", "evp", "avp", "vice", "president", "chief", "cxo", "cio", "cto",
    "ceo", "coo", "cfo", "cmo", "cmio", "cno", "chro", "ciso", "cpo", "cdo",
    # management / lead
    "director", "dir", "head", "manager", "mgr", "management", "lead", "leader",
    "principal", "executive", "exec", "supervisor", "chair", "chairman",
    # rank modifiers
    "senior", "sr", "snr", "junior", "jr", "staff", "associate", "assoc",
    "entry", "entry-level", "intern", "internship", "trainee", "apprentice",
    "deputy", "assistant", "asst",
    # org scope (broadening these lifts recall without changing the field)
    "global", "regional", "national", "corporate", "enterprise", "group",
})

# Connective/filler tokens that are only meaningful between real words; dropped
# when stripping seniority leaves them leading, trailing, or doubled.
_CONNECTIVES = frozenset({"of", "the", "and", "for", "to", "a", "an", "&", "-", "–", "—", ","})

# Tokens that describe a SCHEDULE/scope but are NOT a field of work on their own.
# When de-seniorizing leaves ONLY one of these (e.g. "Shift Supervisor" -> "shift",
# "Night Manager" -> "night", "Team Lead" -> "team"), the stem is a junk query that
# matches everything; the guard (item P3 deseniorize) keeps the original title
# instead. These are only ever a problem as a LONE leftover -- "night shift nurse"
# still keeps "nurse", so multi-token stems are unaffected.
_WEAK_STANDALONE = frozenset({
    "shift", "shifts", "team", "night", "nights", "day", "days", "evening",
    "evenings", "weekend", "weekends", "overnight", "floater", "float", "prn",
    "seasonal", "temporary", "temp", "relief", "on-call", "oncall", "line",
    "area", "unit", "crew", "field", "site", "store", "branch", "office",
    "floor", "zone", "region", "department", "dept", "location", "route",
})

_MIN_KEYWORD_LEN = 3

# Split on whitespace but keep intra-word punctuation (r&d, c++, .net, ui/ux).
_SPLIT = re.compile(r"\s+")


def _tokens(title: str) -> list[str]:
    return [t for t in _SPLIT.split((title or "").strip()) if t]


def deseniorize(title: str) -> str:
    """Return the FIELD stem of a job title: the title with seniority/level and
    org-scope tokens removed, connectives cleaned up, lowercased. May be '' if the
    title was nothing but seniority (e.g. "Director")."""
    kept: list[str] = []
    for raw in _tokens(title):
        tok = raw.lower().strip(",")
        if not tok:
            continue
        if tok in SENIORITY_TOKENS:
            continue
        kept.append(tok)
    # Trim connectives that are now leading/trailing, and collapse an
    # accidental doubled connective ("... of of ...").
    while kept and kept[0] in _CONNECTIVES:
        kept.pop(0)
    while kept and kept[-1] in _CONNECTIVES:
        kept.pop()
    cleaned: list[str] = []
    for tok in kept:
        if tok in _CONNECTIVES and cleaned and cleaned[-1] in _CONNECTIVES:
            continue
        cleaned.append(tok)
    # Guard: if stripping seniority left fewer than one MEANINGFUL noun -- i.e. the
    # only survivor is a schedule/scope modifier ("shift"/"night"/"team"/"line") --
    # the stem is a junk broad query. Return '' so the caller keeps the original
    # title ("Shift Supervisor") as the query instead of "shift". Multi-token
    # stems and real single-word fields ("nurse", "controls engineer") are
    # unaffected. (P3 deseniorize guard)
    meaningful = [t for t in cleaned if t not in _WEAK_STANDALONE
                  and t not in _CONNECTIVES]
    if not meaningful:
        return ""
    return " ".join(cleaned).strip()


def normalize_industry(industry: str) -> str:
    """'health_informatics' / 'Health-Informatics' -> 'health informatics'."""
    s = (industry or "").strip().lower().replace("_", " ").replace("-", " ")
    return re.sub(r"\s+", " ", s).strip()


def effective_keywords(cfg: dict) -> list[str]:
    """The search keywords for a project config, with a genre-safe fallback.

    - Explicit `cfg['keywords']` always win.
    - Otherwise, a project that set a NON-engineering `industry` must NOT silently
      fall back to the engineering DEFAULT_KEYWORDS (that's the bug where a health/
      finance project created via the People/Project button — no wizard — searched
      for engineers). Derive from the field instead: the industry term + its profile
      synonyms/title-terms.
    - An engineering or industry-less project falls back to DEFAULT_KEYWORDS (unchanged).
    """
    from config import DEFAULT_KEYWORDS
    kw = cfg.get("keywords")
    if kw:
        return list(kw)
    industry = (cfg.get("industry") or "").strip()
    if industry:
        try:
            import industry_profile
            p = industry_profile.resolve(industry)
            if not p.eng_like:
                derived = [normalize_industry(industry)] + list(p.query_synonyms)
                derived = [k for k in derived if k]
                if derived:
                    return list(dict.fromkeys(derived))
        except Exception:
            pass
    return list(DEFAULT_KEYWORDS)


def _dedupe_ci(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for it in items:
        k = it.strip().lower()
        if k and k not in seen:
            seen.add(k)
            out.append(k)
    return out


# Cap on the AUTO-ADDED field synonyms only (protects free API tiers). The user's
# own role-derived keywords + the industry term are NEVER truncated, so their
# chosen blast radius is always retained; only extra synonyms are bounded.
_MAX_SYNONYMS = 6


def broad_query_keywords(roles: Iterable[str], industry: str = "",
                         synonyms: Iterable[str] = ()) -> list[str]:
    """Broaden a target-role list into high-recall query keywords.

    - Each role is de-seniorized to its field stem; a role that is nothing but
      seniority falls back to itself (lowercased) so we still query something.
    - The (normalized) industry/field is appended as its own query term.
    - `synonyms` are extra broad FIELD terms (from the industry profile) that WIDEN
      recall; up to _MAX_SYNONYMS new ones are added. They never displace a user term.
    - Results are lowercased, de-duplicated case-insensitively (order preserved),
      and stems shorter than 3 chars are dropped.

    A list of plain IC titles with no seniority tokens and no synonyms is returned
    unchanged (lowercased), so an engineering search is byte-identical to before.
    """
    candidates: list[str] = []
    for role in roles:
        if not role or not role.strip():
            continue
        stem = deseniorize(role)
        if stem and len(stem) >= _MIN_KEYWORD_LEN:
            candidates.append(stem)
        else:
            candidates.append(role.strip().lower())  # fallback: don't drop it
    ind = normalize_industry(industry)
    if ind and len(ind) >= _MIN_KEYWORD_LEN:
        candidates.append(ind)
    base = [k for k in _dedupe_ci(candidates) if len(k) >= _MIN_KEYWORD_LEN]

    # Tier 1: field synonyms the caller passed in (typically the industry
    # profile's own curated `query_synonyms` — seed-authored or O*NET-tier),
    # bounded, never displacing a user term.
    have = set(base)
    added = 0
    for s in synonyms:
        s = (s or "").strip().lower()
        if s and len(s) >= _MIN_KEYWORD_LEN and s not in have:
            base.append(s)
            have.add(s)
            added += 1
            if added >= _MAX_SYNONYMS:
                break

    # Tier 2 (item 26): O*NET related-occupation / alt-title synonyms for the
    # resolved field, LOWER priority than tier 1 — only fills whatever slots
    # tier 1 left under the SAME _MAX_SYNONYMS cap, and never displaces a user
    # term. No-op for eng IC titles / empty industry (industry_profile gates it),
    # so Alex's engineering flow is byte-identical.
    if industry and added < _MAX_SYNONYMS:
        try:
            import industry_profile
            related = industry_profile.related_occupation_titles(industry, exclude=have)
        except Exception:
            related = []
        for s in related:
            s = (s or "").strip().lower()
            if s and len(s) >= _MIN_KEYWORD_LEN and s not in have:
                base.append(s)
                have.add(s)
                added += 1
                if added >= _MAX_SYNONYMS:
                    break
    return base


# ── tech/remote-skewed source gating (item 24) ───────────────────────────────
# RemoteOK, Remotive, Himalayas, Arbeitnow, and HN-whoishiring are remote/tech-
# audience boards at the SOURCE (their own postings skew software/eng), so for a
# hands-on/clinical/trade field they mostly add noise + wasted API calls rather
# than reach. Gated the same way Muse/Jobicy already are (industry_profile), not
# hardcoded per-source.
TECH_SKEWED_SOURCES = frozenset({"remoteok", "remotive", "himalayas", "arbeitnow", "hn",
                                 "weworkremotely", "workingnomads"})


# SOC major groups (2-digit) that are desk/knowledge work -- remote-audience
# boards (RemoteOK/Remotive/Himalayas/...) carry real postings for these:
#   11 management, 13 business/finance ops, 15 computer/math, 17 arch/eng,
#   19 life/physical/social science, 23 legal, 25 education, 27 arts/design/media.
# Deliberately EXCLUDES the hands-on major groups (29 healthcare practitioners,
# 31 healthcare support, 33 protective, 35 food, 37 grounds, 41 sales-floor,
# 43 admin-support, 45 farming, 47 construction, 49 install/repair, 51 production,
# 53 transport) so nursing-clinical / trades / retail keep the remote boards
# gated OFF. Group 29 is handled specially below (it mixes clinical practitioners
# with health-informatics/analytics knowledge roles).
_KNOWLEDGE_SOC_MAJORS = frozenset({"11", "13", "15", "17", "19", "23", "25", "27"})

# Text signals that a field is the KNOWLEDGE side of an otherwise hands-on sector
# (e.g. "health informatics" / "clinical analytics" sit in healthcare but are desk
# jobs a remote board actually posts). Used to (a) rescue the 29-partial case and
# (b) classify fields that don't resolve to a clean SOC code at all.
_KNOWLEDGE_TEXT_SIGNALS = frozenset({
    "informatics", "analytics", "analyst", "data", "science", "administration",
    "administrator", "management", "manager", "coordinator", "consultant",
    "compliance", "quality", "education", "educator", "instructor", "teacher",
    "teaching", "training", "curriculum", "finance", "financial", "accounting",
    "billing", "coding", "revenue", "software", "developer", "engineer",
    "engineering", "it", "technology", "technologist", "systems", "design",
    "marketing", "communications", "policy", "research", "director",
    "information", "informatician",
})

# Hands-on text signals that OVERRIDE a knowledge match when both are present
# (e.g. "clinical nurse educator" is still bedside-adjacent clinical work). Kept
# small and specific so it only fires for clearly hands-on fields.
_HANDSON_TEXT_SIGNALS = frozenset({
    "nurse", "nursing", "rn", "lpn", "cna", "aide", "caregiver", "bedside",
    "phlebotom", "surgical", "therapist", "technician", "welder", "welding",
    "plumber", "plumbing", "electrician", "hvac", "carpenter", "mechanic",
    "driver", "trucking", "warehouse", "custodian", "janitor", "cook", "chef",
    "server", "cashier", "retail", "barista", "housekeep", "landscap",
})


def _text_knowledge_signal(industry: str) -> Optional[bool]:
    """True/False from the industry TEXT alone, or None when it says nothing.
    A hands-on signal wins over a knowledge signal when both appear."""
    toks = set(re.split(r"[\s_\-/,]+", (industry or "").lower()))
    if not toks:
        return None
    if toks & _HANDSON_TEXT_SIGNALS:
        return False
    if toks & _KNOWLEDGE_TEXT_SIGNALS:
        return True
    return None


def is_knowledge_work(industry: str) -> bool:
    """True when the tech/remote-audience boards fit this field.

    Layered signal (first decisive wins), so a field is judged on the strongest
    thing we know about it:
      1. eng_like / mapped-Jobicy -- the original signal Muse/Jobicy already route
         on (empty industry -> eng_like True -> Alex byte-identical).
      2. SOC major group -- a resolved O*NET occupation in a desk/knowledge major
         group (11/13/15/17/19/23/25/27) is knowledge work; a hands-on major group
         (29 clinical, 31 support, 47 construction, 49 repair, 51 production, ...)
         is not. Group 29 is split by the TEXT signal below (informatics/analytics
         = knowledge; bedside nursing = not).
      3. Field TEXT -- informatics/analytics/education/finance/... => knowledge;
         nursing/welding/hvac/driver/... => not. This rescues health-informatics
         and education, which don't resolve to a clean SOC code, while keeping
         nursing-clinical and the trades gated OFF.
      4. Default False for an otherwise-unknown non-eng field (unchanged from the
         previous behavior for fields that gave no signal).
    """
    import industry_profile
    p = industry_profile.resolve(industry)
    if p.eng_like or p.jobicy_industry is not None:
        return True

    soc = None
    try:
        soc = industry_profile.resolve_soc(industry)
    except Exception:
        soc = None
    text_sig = _text_knowledge_signal(industry)
    if soc and soc.get("code"):
        major = soc["code"].split("-")[0]
        if major == "29":
            # Healthcare practitioners: clinical unless the text says informatics/
            # analytics/administration (a desk health role).
            return text_sig is True
        if major in _KNOWLEDGE_SOC_MAJORS:
            return True
        # Resolved to a hands-on major group -> not knowledge work.
        return False

    # No clean SOC match -> fall back to the field text signal.
    return bool(text_sig)


def gate_tech_sources(sources: Iterable[str], industry: str,
                      cfg_sources: dict | None = None) -> list[str]:
    """Drop TECH_SKEWED_SOURCES for a non-knowledge-work field so a plumber/nurse
    search doesn't waste calls on remote-tech boards. An explicit per-source
    `True` in `cfg_sources` (the user's own Settings toggle) always wins and
    keeps a source on regardless of field. Additive: eng/knowledge-work fields
    (and any explicit override) are unaffected."""
    cfg_sources = cfg_sources or {}
    if is_knowledge_work(industry):
        return list(sources)
    return [s for s in sources
           if s not in TECH_SKEWED_SOURCES or cfg_sources.get(s) is True]
