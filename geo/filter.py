"""Metro radius + remote-region filter (spec §5.5).

Built on coverage.geography.metro_variants (WS-1): keep a job whose location
matches any variant of the target metro, keep remote postings gated by region,
and keep unknown/empty locations (don't over-cut the wide net).
"""
from __future__ import annotations

import re

from coverage.geography import metro_variants

# A US-acceptable remote posting (word-boundary so "us" doesn't match australia).
_US_OK_RE = re.compile(r"\b(u\.?s\.?|usa|united states|anywhere)\b", re.I)
_GLOBAL_ONLY = ("worldwide", "global", "anywhere in the world", "international")
# "remote" as a whole word, but NOT the "remote sensing/monitoring" noun compounds.
_REMOTE_RE = re.compile(r"\bremote\b(?!\s+(?:sensing|monitoring|sensors?))", re.I)

# View-filter modes for the Inbox "Location" control (canonical, agnostic). The
# default focuses on the user's home metro but always keeps remote + unknown so
# the wide net isn't over-cut. "All locations" disables the view filter entirely.
LOCATION_MODES = ("Local + remote", "Local only", "All locations")
DEFAULT_LOCATION_MODE = "Local + remote"


def _is_remote(loc: str, title: str) -> bool:
    return bool(_REMOTE_RE.search(loc or "") or _REMOTE_RE.search(title or ""))


def _remote_region_ok(loc: str, remote_region: str | None) -> bool:
    if not remote_region:
        return True
    region = remote_region.strip().lower()
    if region == "us":
        if any(g in loc for g in _GLOBAL_ONLY):
            return False
        return bool(_US_OK_RE.search(loc or ""))
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


def classify(location: str, title: str, area: str, *, remote_ok: bool = True) -> str:
    """Bucket one posting relative to home metro `area`: "local" | "remote" |
    "elsewhere" | "unknown". Pure + agnostic — reuses metro_variants(area)
    (CBSA-based) so it works for any US metro with no hardcoding. A metro match
    wins over a remote tag (a "Cincinnati, OH - Remote" hybrid counts as local).
    With remote_ok=False, remote-only postings drop to "elsewhere"."""
    loc = (location or "").strip().lower()
    ttl = (title or "").lower()
    if not loc:
        return "unknown"
    variants = {v for v in metro_variants(area) if v}
    if any(v in loc for v in variants):
        return "local"
    if _is_remote(loc, ttl):
        return "remote" if remote_ok else "elsewhere"
    return "elsewhere"


def location_visible(location: str, title: str, area: str, mode: str,
                     *, remote_ok: bool = True) -> bool:
    """Should this posting show under the given Inbox Location `mode`?
    Local-focused views always keep "local" and "unknown" (don't over-cut);
    "Local + remote" additionally keeps "remote"; "All locations" keeps all."""
    if mode == "All locations":
        return True
    bucket = classify(location, title, area, remote_ok=remote_ok)
    if bucket in ("local", "unknown"):
        return True
    if bucket == "remote":
        return mode == "Local + remote"
    return False  # elsewhere
