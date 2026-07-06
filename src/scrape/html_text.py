"""Shared HTML-to-text flattening for the ATS scrapers (finding #8).

Every scrape/*_scraper.py client that consumes an HTML-escaped-HTML description
field (Greenhouse, Breezy, Eightfold, JazzHR, Personio, jsonld, Paylocity,
Pinpoint, Oracle ORC, Phenom, Recruitee, Teamtailor, Workable) re-implemented
the identical byte-for-byte one-liner:

    re.sub(r"\\s+", " ", _TAG_RE.sub(" ", html.unescape(raw))).strip()[:3000]

That's now here once. Stdlib-only (re + html), so it's importable from both
scrape/ and search/ with no new dependency or layering risk.

NOT a drop-in for every '_TAG_RE' user in the repo — some sites are genuinely
different (see brain/techdebt-register-2026-07-05.md finding #8's parity
notes): vincere_scraper.py's `_strip_html` skips html.unescape() and the [:3000]
truncation (its `public_description` field isn't HTML-escaped-HTML the same
way), and careeronestop_client.py's inline `_TAG_RE.sub(...)` call skips both
`html.unescape()` and the interior `.strip()` before truncation. Both were left
untouched rather than force-fit onto this helper.
"""
from __future__ import annotations
import html
import re

_TAG_RE = re.compile(r"<[^>]+>")


def strip_html_to_text(raw, limit: int = 3000) -> str:
    """Unescape HTML entities, strip tags, collapse whitespace runs to a single
    space, and truncate to ``limit`` chars. Falsy input (None/''≥) -> ''."""
    if not raw:
        return ""
    return re.sub(r"\s+", " ", _TAG_RE.sub(" ", html.unescape(str(raw)))).strip()[:limit]
