"""Shared heterogeneous ISO-date-string parser (finding #9).

search.freshness, search.search_engine, and match.ghost each duplicated the
identical tolerance loop for parsing a source's date string (ISO with/without
timezone, a trailing ``Z``, or a bare date) into an aware ``datetime``. This is
that loop, extracted once.

Stdlib-only (datetime only) so it's safely importable from match/ghost.py,
which deliberately keeps itself free of any search/scraper import chain.

Each call site keeps its own not-found SENTINEL (``None`` for freshness.py,
an epoch ``datetime`` constant for search_engine.py/ghost.py) — this helper
only does the parse loop and returns ``None`` on failure; callers substitute
their own sentinel. Also NOTE: callers historically differed on whether they
guard non-str truthy input before calling — see ``parse_flex_iso``'s docstring.
"""
from __future__ import annotations
from datetime import datetime, timezone


def parse_flex_iso(value):
    """Parse a heterogeneous ISO-ish date string into an aware ``datetime``, or
    ``None`` if empty/unparseable.

    Tries, in order: the full (whitespace-trimmed, ``Z``->``+00:00``) string,
    just its first 19 chars (drops sub-second/odd trailing junk), then just its
    first 10 (a bare ``YYYY-MM-DD`` date). A naive result is assumed UTC.

    Does NOT itself guard against a non-str truthy ``value`` (e.g. an int or a
    dict) — it will raise on ``.strip()`` exactly as the original
    search_engine.py copy did. Callers that need a stricter guard (freshness.py,
    ghost.py both additionally required ``isinstance(value, str)``) should check
    that themselves before calling, to keep each call site's observable
    behavior unchanged from before the dedup.
    """
    if not value:
        return None
    s = value.strip().replace("Z", "+00:00")
    for candidate in (s, s[:19], s[:10]):
        try:
            dt = datetime.fromisoformat(candidate)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None
