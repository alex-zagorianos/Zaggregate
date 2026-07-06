"""Tiered scrape scheduling — keep the daily run fast as the company registry
grows from hundreds to thousands.

Each company is scraped on a cadence set by how active its board is:
  hot  (recent matching jobs)        -> every run
  warm (reachable, nothing matching) -> ~weekly
  cold (empty / unreachable)         -> ~monthly

A never-seen company is always due, and a HOT company is due every run, so an
active board is never starved — tiering can only defer quiet/dead boards, so it
cannot reduce coverage of the jobs you actually want.

State (last_scraped / last_hit_count / tier) persists in cache/registry_state.json.
The scheduling functions take ``today`` explicitly so they're pure + deterministic
(no hidden clock) and easy to test.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

DEFAULT_INTERVALS = {"hot": 1, "warm": 7, "cold": 30}  # days between scrapes
DEFAULT_STATE_FILENAME = "registry_state.json"


def company_key(company) -> str:
    """Stable per-board key (matches the registry's (ats_type, slug) identity)."""
    return f"{company.ats_type}:{company.slug}"


def classify_tier(last_hit_count, *, reachable: bool = True) -> str:
    """hot if the board returned matching jobs last run, warm if reachable but
    empty, cold if unreachable/errored."""
    if not reachable:
        return "cold"
    if last_hit_count and last_hit_count > 0:
        return "hot"
    return "warm"


def _parse_date(s):
    try:
        return date.fromisoformat((s or "")[:10])
    except (ValueError, TypeError):
        return None


def is_due(entry, today: date, intervals=DEFAULT_INTERVALS) -> bool:
    """Whether a company is due to be scraped. Never-seen (no entry / no date) is
    always due; otherwise due once ``intervals[tier]`` days have passed."""
    if not entry:
        return True
    last = _parse_date(entry.get("last_scraped"))
    if last is None:
        return True
    interval = intervals.get(entry.get("tier", "warm"), DEFAULT_INTERVALS["warm"])
    return (today - last) >= timedelta(days=interval)


def due_companies(companies, state, today: date, intervals=DEFAULT_INTERVALS):
    """The subset of companies due to be scraped this run."""
    return [c for c in companies if is_due(state.get(company_key(c)), today, intervals)]


def update_after_scrape(state: dict, company, hit_count, today: date,
                        *, reachable: bool = True) -> dict:
    """Record a scrape: stamp today, the hit count, and the recomputed tier."""
    state[company_key(company)] = {
        "last_scraped": today.isoformat(),
        "last_hit_count": int(hit_count or 0),
        "tier": classify_tier(hit_count, reachable=reachable),
    }
    return state


def load_state(path) -> dict:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_state(path, state: dict) -> None:
    """Atomic write (reuses the cache helper's temp-file + os.replace)."""
    from scrape.cache_helpers import write_cache
    write_cache(Path(path), state)
