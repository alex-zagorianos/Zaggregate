"""Live yield probe (search-discovery-plan.md §4.2) -- an opt-in, cheap "how many
openings for this term nearby?" check. ONE Adzuna page-1 request with the
smallest possible page size (``results_per_page=1``), reading only the API's
``count`` field. Never JSearch/SerpApi -- those have hard monthly caps already
strained by the daily reach probe; Adzuna's per-minute limiter is the only one
cheap enough to spend on this.

Budget: at most ``BUDGET_PER_DAY`` probes/day, per project, tracked in a small
self-contained JSON file under the project's data dir (no schema change, no
shared-file edits -- this module owns its own counter rather than reaching into
``tracker.db`` or ``http_util.MonthlyQuota``).

The actual network call is isolated behind ``_adzuna_count`` -- the single seam
tests monkeypatch -- so budget math, date rollover, and pool recording stay
pure and network-free.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

import config
import workspace
from search import adzuna_client
from search.discovery import pool
from search.http_util import RateLimiter

BUDGET_PER_DAY = 10

_BUDGET_FILENAME = ".discovery_probe_budget.json"


def _today_str() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _budget_path(slug: str | None) -> Path:
    return workspace.project_dir(slug) / _BUDGET_FILENAME


def _load_budget(slug: str | None) -> dict:
    try:
        return json.loads(_budget_path(slug).read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_budget(slug: str | None, data: dict) -> None:
    # Best-effort, atomic (tmp + os.replace) -- a failed write should never
    # crash a probe; worst case the counter under-persists and a later probe
    # re-reads a slightly-stale "used" value.
    path = _budget_path(slug)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data), encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        pass


def probes_remaining(slug: str | None = None, *, today: str | None = None) -> int:
    """Remaining probe budget for the active (or named) project today. Reads the
    per-project JSON counter, resetting it when the date rolls over. `today` (an
    ISO date string) is injectable for tests."""
    today_s = today or _today_str()
    data = _load_budget(slug)
    if data.get("date") != today_s:
        return BUDGET_PER_DAY
    used = int(data.get("used", 0) or 0)
    return max(0, BUDGET_PER_DAY - used)


def _consume_one(slug: str | None, today_s: str) -> None:
    """Persist one used probe against today's counter, rolling the file over to
    a fresh day first if the stored date is stale."""
    data = _load_budget(slug)
    if data.get("date") != today_s:
        data = {"date": today_s, "used": 0}
    data["used"] = int(data.get("used", 0) or 0) + 1
    _save_budget(slug, data)


def _adzuna_configured() -> bool:
    return bool(config.resolve_secret("ADZUNA_APP_ID", "adzuna_app_id")) and bool(
        config.resolve_secret("ADZUNA_APP_KEY", "adzuna_app_key")
    )


# Process-lifetime limiter at Adzuna's own ceiling (config.ADZUNA_RATE_LIMIT).
# AdzunaClient builds a FRESH RateLimiter per instance (source_registry.py,
# ui/source_keys_core.py both construct their own client) rather than a shared
# process-wide singleton, so there is no live limiter object this module can
# reach into without editing adzuna_client.py. Mirroring http_util's own
# careers_host_limiter lazy-singleton pattern is the documented fallback: this
# serializes THIS process's probe traffic at the same 25/min ceiling the daily
# run's Adzuna client uses, but cannot cross-serialize against a daily_run in a
# SEPARATE process. Flagged as a deviation from "share the exact instance."
_limiter_singleton: RateLimiter | None = None
_limiter_lock = threading.Lock()


def _limiter() -> RateLimiter:
    global _limiter_singleton
    if _limiter_singleton is None:
        with _limiter_lock:
            if _limiter_singleton is None:
                _limiter_singleton = RateLimiter(config.ADZUNA_RATE_LIMIT, quiet=True)
    return _limiter_singleton


def _adzuna_count(term: str, location: str = "") -> int | None:
    """The one live network call this module makes: an Adzuna page-1 request
    with the cheapest possible page (``results_per_page=1``), returning the
    API's ``count`` field. Isolated as a single function so tests monkeypatch
    this exact seam instead of stubbing HTTP.

    Reuses AdzunaClient's credential resolution, country-scoped base_url, and
    retry-enabled session (``search.http_util.make_session`` via the client)
    rather than re-implementing any of that. Only ``results_per_page`` differs
    from ``AdzunaClient.search()``, which hardcodes ``config.
    ADZUNA_RESULTS_PER_PAGE`` (50) -- too expensive for a probe that only wants
    the count, not the rows.
    """
    client = adzuna_client.AdzunaClient(cache_enabled=False)
    _limiter().acquire()
    url = f"{client.base_url}/1"
    params = {
        "app_id": client.app_id,
        "app_key": client.app_key,
        "what": term,
        "results_per_page": 1,
        "content-type": "application/json",
    }
    where = (location or "").strip()
    if where:
        params["where"] = where
    response = client.session.get(url, params=params, timeout=30)
    response.raise_for_status()
    data = response.json()
    count = data.get("count")
    return int(count) if count is not None else None


def probe_yield(
    term: str,
    location: str = "",
    *,
    slug: str | None = None,
    today: str | None = None,
) -> dict:
    """Run ONE Adzuna page-1 count probe for `term` near `location`, decrement the
    daily budget, and record the count via pool.set_yield. Returns:
      {"term": str, "yield_count": int|None, "yield_source": str,
       "probes_remaining_today": int, "skipped": bool, "reason": str}
    - Budget exhausted -> yield_count=None, skipped=True, reason="budget", no network call.
    - Adzuna not configured (no key) -> yield_count=None, skipped=True, reason="no_key".
    - Network/parse error -> yield_count=None, skipped=True, reason="error" (never raises).
    yield_source is like 'adzuna:<where>'. On a real network attempt (success or
    error), one probe is consumed from the daily budget and persisted. Do NOT
    record a probe against the budget when it was skipped for budget/no_key (a
    skipped probe never reached the network, so it consumed nothing)."""
    term_clean = (term or "").strip()
    today_s = today or _today_str()
    where = (location or "").strip()
    source = f"adzuna:{where}"

    remaining = probes_remaining(slug, today=today_s)
    if remaining <= 0:
        return {
            "term": term_clean,
            "yield_count": None,
            "yield_source": "",
            "probes_remaining_today": 0,
            "skipped": True,
            "reason": "budget",
        }

    if not _adzuna_configured():
        return {
            "term": term_clean,
            "yield_count": None,
            "yield_source": "",
            "probes_remaining_today": remaining,
            "skipped": True,
            "reason": "no_key",
        }

    # From here on we're committing to a real network attempt -- consume the
    # budget slot up front so an erroring call still counts (it still spent a
    # real Adzuna hit), not just a successful one.
    _consume_one(slug, today_s)
    remaining_after = probes_remaining(slug, today=today_s)

    try:
        count = _adzuna_count(term_clean, where)
    except Exception:
        return {
            "term": term_clean,
            "yield_count": None,
            "yield_source": "",
            "probes_remaining_today": remaining_after,
            "skipped": True,
            "reason": "error",
        }

    pool.set_yield(term_clean, count, source)
    return {
        "term": term_clean,
        "yield_count": count,
        "yield_source": source,
        "probes_remaining_today": remaining_after,
        "skipped": False,
        "reason": "",
    }


def probe_terms(
    terms: list[str], location: str = "", *, slug: str | None = None
) -> list[dict]:
    """Probe several terms, stopping when the daily budget is exhausted (the rest
    come back skipped/reason='budget'). Returns one result dict per input term."""
    today_s = _today_str()  # pinned once so a batch belongs to one calendar day
    return [
        probe_yield(term, location, slug=slug, today=today_s) for term in (terms or [])
    ]
