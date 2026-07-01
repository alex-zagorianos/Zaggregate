"""Adapter: map the active project's field to each source's own server-side
taxonomy. All the genre knowledge now lives in one place (industry_profile.py);
this module is a thin, back-compatible shim the clients call.

The Muse and Jobicy were hardcoded to the engineering slice server-side, so a
health/finance/trade seeker got 0 results from both no matter their keywords.
Now the category is derived from the field's IndustryProfile.
"""
from __future__ import annotations

from typing import Optional

import industry_profile


def active_industry(explicit: Optional[str] = None) -> str:
    """The industry to tune sources for: explicit arg > active project's config
    `industry` > '' (engineering-default). Best-effort."""
    if explicit is not None:
        return explicit
    try:
        import workspace
        return (workspace.load_config().get("industry") or "").strip()
    except Exception:
        return ""


def themuse_categories(industry: Optional[str] = None) -> list[str]:
    """The Muse `category` params for this field. Eng/empty -> the (corrected)
    engineering categories; mapped field -> its categories; unknown non-eng -> []
    (no filter = fetch ALL categories, narrowed client-side by keyword)."""
    return industry_profile.resolve(active_industry(industry)).muse_categories


def jobicy_industry(industry: Optional[str] = None) -> Optional[str]:
    """Jobicy `industry` slug for this field. Eng/empty -> 'engineering'; mapped ->
    its slug; unmapped non-eng -> None, which the client treats as 'skip Jobicy' (a
    tech-centric board with nothing for this field)."""
    return industry_profile.resolve(active_industry(industry)).jobicy_industry
