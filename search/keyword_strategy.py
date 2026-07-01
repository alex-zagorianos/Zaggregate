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
from typing import Iterable

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


def is_knowledge_work(industry: str) -> bool:
    """True when the tech/remote-audience boards fit this field: the SAME
    eng_like / mapped-Jobicy signal Muse and Jobicy already use to route (an
    unmapped Jobicy industry means 'this tech-centric remote board has nothing
    for this field' — jobicy_client already skips itself on that signal; the
    generic (unmapped) fallback also already skips Jobicy for the same reason).
    Empty industry (Alex/default) -> True, so nothing changes when unconfigured.
    """
    import industry_profile
    p = industry_profile.resolve(industry)
    return p.eng_like or p.jobicy_industry is not None


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
