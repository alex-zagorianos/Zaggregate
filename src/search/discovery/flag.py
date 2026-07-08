"""Marginal-yield / low-activity flagging (Phase 6, §4.2 of
brain/search-discovery-plan.md).

Flags an ACTIVE term as "hasn't found much lately" -- a UI nudge only. Nothing
here EVER changes a term's status; deactivation is always an explicit user
action elsewhere, same "drop != hide" doctrine match/gate.py already uses for
scoring. This module encodes the design review's fatal-flaw fix: a brand-new
chip is NEVER flagged (the min-activation-age guard) -- otherwise every fresh
suggestion would read as "struggling" before it ever had a chance to be probed.
"""
from __future__ import annotations

from datetime import datetime, timezone

from search.discovery import pool


def _parse_dt(value: str) -> datetime:
    """ISO string -> aware datetime, assuming UTC if the string is naive."""
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _unflagged(term: str, reason: str, yield_count: int | None = None) -> dict:
    """Shared shape for every eligible=False / low_activity=False return."""
    return {"term": term, "eligible": False, "low_activity": False,
            "age_days": 0, "yield_count": yield_count, "reason": reason}


def compute_marginal_yield(term: str, *, window_days: int = 7, min_age_days: int = 7,
                            now: str | None = None) -> dict:
    """Assess whether an ACTIVE term looks low-yield. Returns
      {"term": str, "eligible": bool, "low_activity": bool, "age_days": int,
       "yield_count": int|None, "reason": str}

    Rules (both must hold for low_activity=True):
      - the term has been active >= min_age_days (a brand-new chip is NEVER
        flagged -- the min-activation-age guard). If younger, eligible=False.
      - its available activity signal is zero/low.

    TODO(§4.2): real provenance-based marginal_unique_7d (a dedup'd unique-yield
    count over window_days, sourced from inbox provenance tagging) isn't wired
    yet. Until then this uses the best AVAILABLE signal: the term's last
    live-probed yield_count (0 or None => low). window_days is accepted now so
    callers don't need a signature change once the real windowed signal lands.

    `now` (ISO datetime string) is injectable for testable age math. Never
    raises; a non-active or unknown term -> eligible=False, low_activity=False.
    """
    term = (term or "").strip()
    if not term:
        return _unflagged(term, "blank term")

    row = pool.get_term(term)
    if row is None:
        return _unflagged(term, "unknown term")
    if row["status"] != "active":
        return _unflagged(term, f"not active (status={row['status']!r})", row.get("yield_count"))

    activated_at = row.get("activated_at")
    if not activated_at:
        return _unflagged(term, "active but missing activated_at", row.get("yield_count"))

    try:
        activated_dt = _parse_dt(activated_at)
        now_dt = _parse_dt(now) if now else datetime.now(timezone.utc)
        age_days = (now_dt - activated_dt).days
    except (ValueError, TypeError):
        return _unflagged(term, "unparseable timestamp", row.get("yield_count"))

    yield_count = row.get("yield_count")

    if age_days < min_age_days:
        return {"term": term, "eligible": False, "low_activity": False,
                "age_days": age_days, "yield_count": yield_count,
                "reason": f"active only {age_days}d < min_age_days={min_age_days} "
                          "(min-activation-age guard)"}

    low = yield_count is None or yield_count == 0
    reason = ("zero/unknown probed yield_count (proxy for marginal_unique_7d)"
              if low else f"last probed yield_count={yield_count}")
    return {"term": term, "eligible": True, "low_activity": low,
            "age_days": age_days, "yield_count": yield_count, "reason": reason}


def low_activity_terms(*, min_age_days: int = 7, now: str | None = None) -> list[dict]:
    """Run compute_marginal_yield over every ACTIVE term; return only those with
    low_activity=True. This is the list the UI shows as gentle 'hasn't found much
    lately' nudges -- it NEVER changes any term's status."""
    out = []
    for row in pool.get_pool(status="active"):
        result = compute_marginal_yield(row["term"], min_age_days=min_age_days, now=now)
        if result["low_activity"]:
            out.append(result)
    return out
