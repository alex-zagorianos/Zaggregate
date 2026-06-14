"""Shared keyword matching for career-page scrapers (greenhouse/lever/direct).

The old per-scraper fallback was any(token in haystack), so the bare token
"engineer" matched every engineering job on a board — Veeva alone returned
200+ "matches" per keyword. The fallback now requires ALL significant tokens.
"""


def keyword_matches(keyword: str, haystack: str) -> bool:
    """True if `keyword` matches `haystack` (case-insensitive).

    Exact phrase match wins. Otherwise every significant token (>=3 chars)
    must appear; a trailing 's' is stripped from longer tokens so
    "controls engineer" still matches "Control Systems Engineer".
    """
    kw = keyword.lower().strip()
    hay = haystack.lower()
    if kw in hay:
        return True
    tokens = [t.rstrip("s") if len(t) > 3 else t
              for t in kw.split() if len(t) >= 3]
    if not tokens:
        return False
    return all(t in hay for t in tokens)
