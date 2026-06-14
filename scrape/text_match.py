"""Shared keyword matching for career-page scrapers (greenhouse/lever/direct).

Delegates to the boolean query engine (search.query), so a `keyword` may use
"exact phrase", OR, NOT/-, and ( ) grouping. A plain keyword with no operators
behaves exactly as before: every significant token must appear (trailing 's'
stripped from longer words), so "controls engineer" still matches "Control
Systems Engineer" and the bare token "engineer" no longer matches everything.
"""
from search.query import parse


def keyword_matches(keyword: str, haystack: str) -> bool:
    """True if the boolean `keyword` query matches `haystack` (case-insensitive)."""
    return parse(keyword).matches(haystack)
