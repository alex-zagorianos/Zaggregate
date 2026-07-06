"""Source-independence declaration for capture-recapture coverage math.

Capture-recapture treats each source as an independent capture occasion: the
overlap between sources is what reveals the unseen population. That inference is
only valid when the sources are actually independent. Two of JobScout's sources
are NOT — SerpApi's ``google_jobs`` engine and JSearch both resolve to the same
upstream (Google-for-Jobs aggregation), so a job "found by both" is one capture,
not two. Counting them as two independent captures inflates the estimated overlap
and makes coverage look better than it is (the single biggest correctness risk in
the coverage estimate — see brain/research-2026-07-01-reach-SYNTHESIS.md).

This module maps each raw source id to an INDEPENDENCE FAMILY and collapses a set
of sources to the set of families that produced a job. Everything not explicitly
grouped is its own family (the safe default: assume independent unless we know
otherwise). Mirrors the GOOD/BAD-pair docstring discipline already in
coverage/registry_coverage.py.
"""
from __future__ import annotations

# raw source_api / source id  ->  independence family.
# Only sources KNOWN to share an upstream index are grouped. Add here when a new
# aggregator is wired that re-syndicates an index another source already reads.
SOURCE_FAMILY: dict[str, str] = {
    # Google-for-Jobs meta-source: both read the same Google Jobs aggregation.
    "serpapi": "google_jobs",
    "jsearch": "google_jobs",
}


def family_of(source_id: str) -> str:
    """Independence family for one raw source id. Unknown/blank -> itself (its own
    family), so an unmapped source is treated as independent."""
    s = (source_id or "").strip().lower()
    return SOURCE_FAMILY.get(s, s)


def collapse_sources(source_ids) -> frozenset:
    """Collapse a set of raw source ids to the set of independence families that
    produced the job. Empty ids are dropped. Used to build the per-job membership
    frozenset for the capture-recapture estimators so correlated sources count as
    one occasion, not several."""
    return frozenset(family_of(s) for s in (source_ids or ()) if (s or "").strip())
