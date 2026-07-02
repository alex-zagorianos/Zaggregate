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


# ── sector-feed gating (E2) ───────────────────────────────────────────────────
# The sector RSS clients (higheredjobs/rnjobsite/jobsacuk) are added to the
# daily net but must be INERT for the wrong field: a welder's project must never
# poll nursing feeds; an education field gets HigherEd automatically. Each client
# owns its own industry->activate decision (its module-level helper), so the same
# knowledge lives with the client. These thin wrappers let daily_run / the CLI
# ask "does this sector source apply to this field?" without importing each client
# module directly, mirroring the themuse/jobicy shims above.


def higheredjobs_active(industry: Optional[str] = None) -> bool:
    """True when HigherEdJobs should poll for this field (an education-family
    industry). Empty/eng industry -> False (inert). Best-effort."""
    from search.higheredjobs_client import _categories_for_industry
    return bool(_categories_for_industry(active_industry(industry)))


def rnjobsite_active(industry: Optional[str] = None) -> bool:
    """True when RNJobSite should poll for this field (a nursing/clinical
    industry). Empty/eng industry -> False (inert). Best-effort."""
    from search.rnjobsite_client import _should_poll
    return _should_poll(active_industry(industry))


def reap_active(industry: Optional[str] = None,
                location: Optional[str] = None) -> bool:
    """True when REAP should poll: an education-family field AND a location in a
    REAP-covered state (CT/MO/NM/OH/PA). Empty/eng industry, or an education
    seeker outside those states, -> False (inert). Best-effort."""
    from search.reap_client import _is_education, portal_for_location
    if not _is_education(active_industry(industry)):
        return False
    return portal_for_location(location) is not None


def edjoin_active(industry: Optional[str] = None) -> bool:
    """True when EdJoin should poll for this field (an education-family industry).
    EdJoin is California-centric and returns 0 gracefully for non-CA metros, so
    the gate is industry-only (location filtering happens in the client). Empty/
    eng industry -> False (inert). Best-effort."""
    from search.edjoin_client import _is_education
    return _is_education(active_industry(industry))


def sector_feed_applies(source: str, industry: Optional[str] = None,
                        location: Optional[str] = None) -> bool:
    """Does a sector `source` apply to this field/location? For sources with no
    industry gate (or unknown), returns True (no-op). jobsacuk is opt-in (handled
    at build time, not here) so it always returns True from this gate."""
    s = (source or "").strip().lower()
    if s == "higheredjobs":
        return higheredjobs_active(industry)
    if s == "rnjobsite":
        return rnjobsite_active(industry)
    if s == "reap":
        return reap_active(industry, location)
    if s == "edjoin":
        return edjoin_active(industry)
    return True
