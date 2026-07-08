"""Search Discovery — the keyword-pool subsystem (ZAG search-discovery plan).

Turns "I want a job" into a rich, high-recall, correctly-scoped keyword set,
with or without an AI, without the user needing to know their industry's title
vocabulary. Split into single-concern submodules so the pieces are independently
testable and were buildable in parallel:

  * ``pool``    — the ``keyword_pool`` SQLite store + its CRUD (the shared spine;
                  every other submodule reads/writes through it).
  * ``propose`` — offline suggestion tiers (core/adjacent/exploratory) from the
                  bundled O*NET taxonomy. Zero network, works on a cold install.
  * ``probe``   — opt-in live "openings nearby" yield check (one Adzuna call).
  * ``mine``    — corpus mining from already-fetched feed caches + the inbox.
  * ``flag``    — marginal-yield / low-activity flagging + suggestion pruning.
  * ``levels``  — experience-level query-phrasing variants (entry/mid only).

Contract with the rest of the app: ``cfg['keywords']`` stays the single source of
truth for what is actually searched. An ``active`` row in ``keyword_pool``
MIRRORS that list; nothing here silently changes what gets searched, and nothing
here ever DROPS a job (inclusion-over-precision). ``pool`` is re-exported here for
convenience; submodules import each other directly.
"""
from __future__ import annotations

from .pool import (  # noqa: F401 — re-exported public API
    VALID_STATUSES,
    VALID_TIERS,
    active_terms,
    get_pool,
    get_term,
    prune_suggestions,
    set_status,
    set_yield,
    upsert_terms,
)

# Re-export the concern submodules so callers can `from search.discovery import
# propose, probe, mine, flag, levels` and so importing the package doubles as an
# import smoke-test (a broken submodule fails loudly here, not deep in a caller).
from . import flag, levels, mine, probe, propose  # noqa: F401,E402
