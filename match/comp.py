"""Compensation normalizer — surface the pay a job DISCLOSES, from the fields
JobScout already has, with zero API calls. Drives a GUI comp column and a
"meets my floor" filter.

The same posting reaches us in two shapes: a ``JobResult`` (salary_min/max +
description) and an inbox-row dict (those, plus a raw ``salary_text`` the GUI
form / browser extension captured). Rather than scatter "where is the pay?"
logic across both call sites, ``normalize_comp`` answers it once:

    1. explicit ``salary_min`` / ``salary_max`` (the scorer already recovers
       description ranges INTO these fields, so prefer them),
    2. else recover from ``salary_text`` (inbox rows only),
    3. else recover from ``description``,
    via match.scorer.salary_from_text for (2) and (3).

``disclosed`` is True iff any min or max was found. ``display`` is a compact
human string for the comp column:

    "$120,000–$140,000"   both ends
    "$120,000+"           one end only (min-or-max)
    "Not listed"          nothing disclosed

``meets_floor`` powers the filter: floor None/0 lets everything through; a
positive floor passes only jobs whose disclosed max-or-min clears it. A job with
NO disclosed comp returns False — undisclosed is not the same as "meets" (the
match scorer treats unlisted pay as neutral *for ranking*; the floor FILTER is a
hard gate, so it must exclude the unknown).

Deterministic, no I/O, no network, stdlib + match.scorer only.
"""
from typing import Optional

from match.scorer import salary_from_text


def _get(job, key):
    """Read ``key`` off either a JobResult (attr) or an inbox-row dict, returning
    None when absent. Never raises."""
    if job is None:
        return None
    if isinstance(job, dict):
        return job.get(key)
    return getattr(job, key, None)


def _coerce(value) -> Optional[float]:
    """A salary field -> float, or None if absent/blank/non-numeric."""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _recover(job) -> tuple[Optional[float], Optional[float]]:
    """(min, max) from explicit fields, else salary_text, else description."""
    lo = _coerce(_get(job, "salary_min"))
    hi = _coerce(_get(job, "salary_max"))
    if lo is not None or hi is not None:
        return lo, hi
    # Inbox rows carry the raw captured string; JobResults don't have the attr.
    text = _get(job, "salary_text")
    if text:
        lo, hi = salary_from_text(text)
        if lo is not None or hi is not None:
            return lo, hi
    description = _get(job, "description")
    if description:
        lo, hi = salary_from_text(description)
        if lo is not None or hi is not None:
            return lo, hi
    return None, None


def _display(lo: Optional[float], hi: Optional[float]) -> str:
    """Compact comp string for the GUI column."""
    if lo is not None and hi is not None:
        return f"${lo:,.0f}–${hi:,.0f}"
    single = lo if lo is not None else hi
    if single is not None:
        return f"${single:,.0f}+"
    return "Not listed"


def normalize_comp(job) -> dict:
    """Normalize whatever pay a job DISCLOSES into a uniform dict.

    Accepts a JobResult or an inbox-row dict. Returns::

        {"min": float|None, "max": float|None, "disclosed": bool, "display": str}

    ``disclosed`` is True iff any min or max was found; ``display`` is one of
    "$120,000–$140,000" / "$120,000+" / "Not listed".
    """
    lo, hi = _recover(job)
    disclosed = lo is not None or hi is not None
    return {
        "min": lo,
        "max": hi,
        "disclosed": disclosed,
        "display": _display(lo, hi),
    }


def meets_floor(job, floor: Optional[int]) -> bool:
    """True if the job clears a pay floor.

    No floor (None or 0) -> always True. Otherwise the job's disclosed
    max-or-min must be >= ``floor``. A job with NO disclosed comp returns False:
    the floor is a hard filter, and undisclosed pay is not a pass.
    """
    if not floor:
        return True
    comp = normalize_comp(job)
    if not comp["disclosed"]:
        return False
    top = comp["max"] if comp["max"] is not None else comp["min"]
    return top is not None and top >= floor
