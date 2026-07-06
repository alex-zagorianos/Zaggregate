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

from match.scorer import parse_comp, salary_from_text

# ISO currency -> display symbol (falls back to the code for anything else).
_CUR_SYMBOL = {"USD": "$", "GBP": "£", "EUR": "€"}
# Canonical pay period -> compact display suffix (annual = no suffix).
_PERIOD_SUFFIX = {"hour": "/hr", "week": "/wk", "month": "/mo", "year": ""}


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


def _recover(job) -> dict:
    """Normalized comp fields from explicit salary_min/max (annual USD), else the
    raw salary_text, else the description. Returns a dict with annualized min/max
    plus the disclosed currency + period + raw (native-period) figures used for
    display. Explicit fields carry no currency/period metadata, so they are treated
    as annual USD (unchanged behavior)."""
    lo = _coerce(_get(job, "salary_min"))
    hi = _coerce(_get(job, "salary_max"))
    if lo is not None or hi is not None:
        return {"min": lo, "max": hi, "raw_min": lo, "raw_max": hi,
                "currency": "USD", "period": "year"}
    # Inbox rows carry the raw captured string; JobResults don't have the attr.
    for src in (_get(job, "salary_text"), _get(job, "description")):
        if not src:
            continue
        comp = parse_comp(src)
        if comp is not None:
            return comp
    return {"min": None, "max": None, "raw_min": None, "raw_max": None,
            "currency": "USD", "period": "year"}


def _fmt(amount: float, currency: str, period: str) -> str:
    sym = _CUR_SYMBOL.get(currency, currency + " ")
    suffix = _PERIOD_SUFFIX.get(period, "")
    # Sub-annual (hourly/weekly/monthly) figures are small -> keep cents so a
    # "$14.50/hr" reads right; annual figures round to whole units.
    if period != "year" and amount < 1000:
        return f"{sym}{amount:,.2f}{suffix}"
    return f"{sym}{amount:,.0f}{suffix}"


def _display(lo, hi, currency: str, period: str, raw_lo, raw_hi) -> str:
    """Compact comp string for the GUI column, in the DISCLOSED currency + period
    (e.g. "$14.50/hr", "£90,000+", "$120,000–$140,000")."""
    a = raw_lo if raw_lo is not None else lo
    b = raw_hi if raw_hi is not None else hi
    if a is not None and b is not None:
        return f"{_fmt(a, currency, period)}–{_fmt(b, currency, period)}"
    single = a if a is not None else b
    if single is not None:
        # A period-suffixed single figure ("$14.50/hr") reads as a rate, not a
        # floor, so no trailing "+"; annual single figures keep the "$120,000+".
        if period != "year":
            return _fmt(single, currency, period)
        return f"{_fmt(single, currency, period)}+"
    return "Not listed"


def normalize_comp(job) -> dict:
    """Normalize whatever pay a job DISCLOSES into a uniform dict.

    Accepts a JobResult or an inbox-row dict. Returns::

        {"min": float|None, "max": float|None, "disclosed": bool, "display": str,
         "currency": str, "period": str}

    ``min``/``max`` are ANNUALIZED (for the floor filter); ``display`` shows the
    disclosed currency + period ("$14.50/hr", "£90,000+", "$120,000–$140,000" /
    "Not listed"). ``disclosed`` is True iff any annualized min or max was found.
    """
    rec = _recover(job)
    lo, hi = rec["min"], rec["max"]
    disclosed = lo is not None or hi is not None
    return {
        "min": lo,
        "max": hi,
        "disclosed": disclosed,
        "display": _display(lo, hi, rec["currency"], rec["period"],
                            rec["raw_min"], rec["raw_max"]),
        "currency": rec["currency"],
        "period": rec["period"],
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
