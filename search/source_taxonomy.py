"""Map a project's field/industry to each source's own server-side taxonomy.

Two free multi-industry sources — The Muse and Jobicy — were hardcoded to request
ONLY the engineering slice server-side (config.THEMUSE_CATEGORIES / JOBICY_INDUSTRY),
so a health/finance/trade seeker got 0 results from them no matter their keywords
(measured 2026-07-01 for a health-informatics search). These helpers derive the
right category/industry from the active project's industry, and stay byte-identical
for an engineering (or unset) industry so Alex's flow is unchanged.
"""
from __future__ import annotations

from typing import Optional

from config import THEMUSE_CATEGORIES
from discover.enumerate import _industry_tokens, is_eng_like


def active_industry(explicit: Optional[str] = None) -> str:
    """The industry to tune sources for: an explicit arg wins, else the active
    project's config `industry`, else '' (engineering-default). Best-effort."""
    if explicit is not None:
        return explicit
    try:
        import workspace
        return (workspace.load_config().get("industry") or "").strip()
    except Exception:
        return ""


# The Muse's real category names (v2 API). Only mappings we've verified against the
# live API are listed; an unmapped non-eng industry sends NO category (fetch all,
# then keyword-filter) rather than a guessed-wrong category that would return 0.
_MUSE_CATEGORIES = {
    "health": ["Healthcare"],
    "clinical": ["Healthcare"],
    "medical": ["Healthcare"],
    "informatics": ["Healthcare", "Data and Analytics"],
    "nursing": ["Healthcare"],
    "data": ["Data and Analytics"],
    "analytics": ["Data and Analytics"],
    "finance": ["Accounting and Finance"],
    "accounting": ["Accounting and Finance"],
    "design": ["Design and UX"],
    "marketing": ["Marketing and PR"],
    "sales": ["Sales"],
    "hr": ["HR"],
    "legal": ["Legal"],
    "education": ["Education"],
}

# Jobicy industry slugs. Jobicy is a tech-centric remote board; for fields it does
# not serve (health), forcing its `medical` slug returns 0, so we omit the param
# (fetch all remote, keyword-filter) instead — strictly better than a 0-yield slug.
_JOBICY_INDUSTRY = {
    "finance": "finance",
    "accounting": "finance",
    "business": "business",
    "marketing": "marketing",
    "design": "design",
    "sales": "sales",
    "hr": "hr",
    "data": "data-science",
    "analytics": "data-science",
    "product": "product",
    "legal": "legal",
    "admin": "admin",
}


def themuse_categories(industry: Optional[str] = None) -> list[str]:
    """The Muse `category` params for this industry. Eng/empty → the original eng
    categories (byte-identical). Mapped non-eng → its categories. Unmapped non-eng
    → [] (no category filter = all categories, narrowed client-side by keyword)."""
    ind = active_industry(industry)
    if not ind or is_eng_like(ind):
        return list(THEMUSE_CATEGORIES)
    cats: list[str] = []
    for tok in _industry_tokens(ind):
        for c in _MUSE_CATEGORIES.get(tok, []):
            if c not in cats:
                cats.append(c)
    return cats  # [] → caller sends no category param (fetch all)


def jobicy_industry(industry: Optional[str] = None) -> Optional[str]:
    """Jobicy `industry` slug for this industry. Eng/empty → 'engineering'
    (byte-identical). Mapped → its slug. Unmapped non-eng → None, which the client
    treats as 'skip Jobicy' (a tech-centric board with nothing for this field)
    rather than pull the whole feed to keyword-filter it to ~0."""
    ind = active_industry(industry)
    if not ind or is_eng_like(ind):
        return "engineering"
    for tok in _industry_tokens(ind):
        if tok in _JOBICY_INDUSTRY:
            return _JOBICY_INDUSTRY[tok]
    return None
