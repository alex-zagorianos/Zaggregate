"""Prune dead (HTTP 404) postings from an inbox.

Career postings close after days–weeks, but inbox rows live until the user
tracks or dismisses them, so dead links accumulate. This probes each career
inbox row against its ATS's API and DELETEs only those that return a DEFINITIVE
404. Timeouts / connection errors / non-404 failures are treated as "unknown"
and the row is KEPT — we never delete on a transient blip.

Unlike scrape.company_health (which debounces with a consecutive-miss streak),
a single confirmed 404 is authoritative for a specific posting, so there is
nothing to debounce. Aggregator rows (adzuna, hn, themuse, …) and Workday/direct
portals aren't reliably probeable and are left untouched.

CLI: `py -m search.cli --prune-inbox [--project SLUG] [--dry-run]`.
"""
import re
import sqlite3
from typing import Callable, Optional
from urllib.parse import urlsplit

import requests

from config import CAREERS_REQUEST_TIMEOUT
from scrape import greenhouse_url
from tracker.db import current_db_path

_UA = {"User-Agent": "Mozilla/5.0 (zaggregate inbox-health probe)"}
_GH_JOB = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs/{token}"
_LEVER_JOB = "https://api.lever.co/v0/postings/{slug}/{token}?mode=json"
_LEVER_RE = re.compile(r"lever\.co/(?P<slug>[^/]+)/(?P<token>[^/?#]+)")
_ASHBY_BOARD = "https://api.ashbyhq.com/posting-api/job-board/{org}"
_ASHBY_RE = re.compile(r"jobs\.ashbyhq\.com/(?P<org>[^/]+)/(?P<jobid>[^/?#]+)")


def _ashby_alive(url: str):
    """True/False/None for an Ashby posting via the org board API (the SPA page
    itself returns 200 for any path). None = unknown -> keep."""
    m = _ASHBY_RE.search(url)
    if not m:
        return None
    try:
        r = requests.get(_ASHBY_BOARD.format(org=m["org"]),
                         timeout=CAREERS_REQUEST_TIMEOUT, headers=_UA)
    except requests.RequestException:
        return None
    if not r.ok:
        return None
    try:
        ids = {p.get("id") for p in (r.json().get("jobs") or [])}
    except ValueError:
        return None
    return m["jobid"] in ids


# Inbox `source` values produced by the career-page scrapers (greenhouse / lever
# / ashby / workday / direct all set source_api="careers"). Only these are probed.
_CAREERS_SOURCES = {"careers"}


def _status(url: str) -> Optional[bool]:
    """GET `url`; True if alive, False on a 404, None on anything else."""
    try:
        r = requests.get(url, timeout=CAREERS_REQUEST_TIMEOUT, headers=_UA)
    except requests.RequestException:
        return None
    if r.status_code == 404:
        return False
    return True if r.ok else None


def _probe(url: str) -> Optional[bool]:
    """True (alive) / False (definitively 404) / None (unknown — keep) for a
    career posting URL, dispatched to the right ATS API by host."""
    host = urlsplit(url).netloc.lower()

    gh = greenhouse_url.parse(url)
    if gh and gh[0] and gh[1]:                       # need both slug and token
        return _status(_GH_JOB.format(slug=gh[0], token=gh[1]))

    if "lever.co" in host:
        m = _LEVER_RE.search(url)
        return _status(_LEVER_JOB.format(slug=m["slug"], token=m["token"])) if m else None

    if "ashbyhq.com" in host:
        # The Ashby SPA returns 200 for any path, so probe board-API membership.
        return _ashby_alive(url)

    # Workday / direct portals / aggregators: not reliably probeable.
    return None


def prune_inbox(
    db_path=None,
    probe: Callable[[str], Optional[bool]] = _probe,
    dry_run: bool = False,
    sources=_CAREERS_SOURCES,
    project: Optional[str] = None,
) -> list[dict]:
    """Probe every career inbox row; DELETE the ones that 404. Returns the list
    of removed rows as {title, company, url}. With dry_run=True, reports what
    WOULD be removed without deleting.

    Resolves the target project ONCE and pins it for the whole (slow, network-
    bound) probe loop, so a concurrent GUI project switch / daily_run can't
    redirect current_db_path() mid-run and make us delete rows from a DIFFERENT
    project's inbox (the S27 cross-project write class). An explicit `db_path`
    still wins and skips pinning; `project` overrides the active slug. The prior
    process pin is restored on exit."""
    import workspace

    if db_path is not None:
        # Caller gave an authoritative DB; do NOT touch the process pin.
        return _prune_inbox_at(db_path, probe, dry_run, sources)

    prior_pin = workspace._PINNED_SLUG
    # Pin the resolved slug once so every current_db_path() below is stable.
    workspace.pin_active(project or workspace.active_slug())
    try:
        return _prune_inbox_at(current_db_path(), probe, dry_run, sources)
    finally:
        workspace.pin_active(prior_pin)


def _prune_inbox_at(db_path, probe, dry_run, sources) -> list[dict]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, title, company, url, source FROM inbox"
    ).fetchall()

    removed: list[dict] = []
    for r in rows:
        if sources and r["source"] not in sources:
            continue
        if not r["url"]:
            continue
        if probe(r["url"]) is False:
            removed.append({"title": r["title"], "company": r["company"], "url": r["url"]})
            if not dry_run:
                conn.execute("DELETE FROM inbox WHERE id=?", (r["id"],))
    if not dry_run:
        conn.commit()
    conn.close()
    return removed
