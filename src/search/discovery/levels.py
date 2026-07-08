"""Experience-level query-phrasing variants (Phase 7, §4.3 of
brain/search-discovery-plan.md).

Pure suggestion generator -- the caller (API/activate flow) upserts the
returned rows into keyword_pool; this module never writes to the pool itself.

HARD SAFETY RULE: only entry/mid ever produce variants. senior/manager/exec
return [] always -- keyword_strategy.deseniorize() [src/search/keyword_strategy.py:67]
exists precisely because appending seniority/level tokens to a title collapses
recall on Adzuna/USAJobs (phrase-matched keyword search: "Senior Controls
Engineer" returns far fewer hits than the field stem "controls engineer").
Generating a "Senior {title}" variant here would reintroduce exactly the
recall collapse deseniorize() was built to guard against, so this is a hard
invariant, not a heuristic -- pinned by
test_no_query_variants_for_senior_manager_exec.
"""
from __future__ import annotations

_ENTRY_MID = frozenset({"entry", "mid"})

# Wizard dropdown labels (case-insensitive) -> canonical level. Anything not
# listed here passes through unchanged and simply fails the entry/mid check
# below -- no need to enumerate every non-generating alias.
_LEVEL_ALIASES = {
    "entry": "entry",
    "entry level": "entry",
    "entry-level": "entry",
    "mid": "mid",
    "senior": "senior",
    "manager": "manager",
    "manager/exec": "manager",
    "exec": "manager",
}


def _normalize_level(level: str) -> str:
    s = (level or "").strip().lower()
    return _LEVEL_ALIASES.get(s, s)


def _variants_for(term: str, alias: str) -> list[str]:
    if alias == "entry":
        return [f"Junior {term}", f"Associate {term}", f"Entry Level {term}", f"{term} I"]
    if alias == "mid":
        return [f"{term} II", f"Associate {term}"]
    return []


def level_query_variants(core_terms: list[str], level: str) -> list[dict]:
    """Generate experience-phrasing variants of core job titles as SUGGESTED pool
    candidates. Returns [{"term": str, "tier": "exploratory",
    "source": "level_variant", "status": "suggested"}...] (deduped, excluding any
    term identical to an input).

    CRITICAL SAFETY RULE: only 'entry' and 'mid' produce variants. 'senior',
    'manager', 'exec' (and blank/unknown) produce an EMPTY list.

    entry -> prefixes like 'Junior {t}', 'Associate {t}', 'Entry Level {t}', '{t} I'.
    mid  -> a light set ('{t} II', 'Associate {t}') -- kept small deliberately.

    Level aliasing: accept the wizard labels too ('Entry','Mid','Senior',
    'Manager/Exec') case-insensitively, mapping to entry/mid/senior/manager.
    Never raises on ordinary bad input (blank/unknown level, empty term list)."""
    alias = _normalize_level(level)
    if alias not in _ENTRY_MID:
        return []

    cleaned = [str(t or "").strip() for t in (core_terms or [])]
    cleaned = [t for t in cleaned if t]
    if not cleaned:
        return []

    input_lower = {t.lower() for t in cleaned}
    seen_lower: set[str] = set()
    out: list[dict] = []
    for term in cleaned:
        for variant in _variants_for(term, alias):
            v_lower = variant.lower()
            if v_lower in input_lower or v_lower in seen_lower:
                continue
            seen_lower.add(v_lower)
            out.append({"term": variant, "tier": "exploratory",
                        "source": "level_variant", "status": "suggested"})
    return out
