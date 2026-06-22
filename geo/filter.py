"""Metro radius + remote-region filter (spec §5.5).

Built on coverage.geography.metro_variants (WS-1): keep a job whose location
matches any variant of the target metro, keep remote postings gated by region,
and keep unknown/empty locations (don't over-cut the wide net).
"""
from __future__ import annotations

from coverage.geography import metro_variants

# Tokens that signal a US-acceptable remote posting.
_US_OK = ("us", "u.s", "united states", "usa", "anywhere", "remote")
_GLOBAL_ONLY = ("worldwide", "global", "anywhere in the world", "international")


def _is_remote(loc: str, title: str) -> bool:
    return "remote" in loc or "remote" in title


def _remote_region_ok(loc: str, remote_region: str | None) -> bool:
    if not remote_region:
        return True
    region = remote_region.strip().lower()
    if region == "us":
        if any(g in loc for g in _GLOBAL_ONLY):
            return False
        return any(tok in loc for tok in _US_OK)
    return region in loc


def filter_to_metro(jobs: list, area: str, *, remote_region: str | None = None) -> list:
    variants = {v for v in metro_variants(area) if v}
    out = []
    for j in jobs:
        loc = (getattr(j, "location", "") or "").strip().lower()
        title = (getattr(j, "title", "") or "").lower()
        if not loc:
            out.append(j)          # unknown location: keep (don't over-cut)
            continue
        if _is_remote(loc, title):
            if _remote_region_ok(loc, remote_region):
                out.append(j)
            continue
        if any(v in loc for v in variants):
            out.append(j)
    return out
