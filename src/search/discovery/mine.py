"""Corpus mining — derive candidate keywords from the user's OWN data
(search-discovery-plan.md §4.2).

Two frequency signals, combined into one map:
  1. A batched SQL scan of ``inbox.title`` + ``applications.title`` — the
     highest-trust signal, since these are real postings the user's own
     search already surfaced or that they chose to track.
  2. Best-effort titles pulled from the on-disk caches the single-feed
     clients (RemoteOK/Remotive/TheMuse/etc.) already persist, via each
     client's ``cached_titles()`` (see ``search.single_feed_client``). A
     source with an empty or unreadable cache just contributes nothing.

STRICTLY OPT-IN: gated behind ``cfg.get('discovery_enabled', False)`` so a
user who has never opened the Discovery panel pays zero cost — no DB scan,
no cache read, nothing upserted. Never raises: any DB/cache/parse hiccup
degrades to "found nothing" rather than propagating.
"""
from __future__ import annotations

import importlib
import re
from collections import Counter

import workspace
from search.discovery import pool
from tracker import db

_WS_RE = re.compile(r"\s+")

# The known keyless single-feed clients (module, class name). Constructed
# on demand, each independently guarded — a source that can't be imported or
# instantiated offline is skipped, never fatal to the others.
_FEED_CLIENTS = (
    ("search.themuse_client", "TheMuseClient"),
    ("search.remoteok_client", "RemoteOKClient"),
    ("search.remotive_client", "RemotiveClient"),
    ("search.jobicy_client", "JobicyClient"),
    ("search.arbeitnow_client", "ArbeitnowClient"),
    ("search.weworkremotely_client", "WeWorkRemotelyClient"),
    ("search.workingnomads_client", "WorkingNomadsClient"),
    ("search.himalayas_client", "HimalayasClient"),
    ("search.hn_client", "HNClient"),
)


def _normalize_title(title) -> str:
    """Light normalization for frequency counting: strip + collapse internal
    whitespace. Case is preserved (these become display strings in the pool)."""
    return _WS_RE.sub(" ", str(title or "").strip())


def _sql_title_counts() -> Counter:
    """Raw, unfiltered frequency Counter of normalized titles across
    ``inbox`` + ``applications`` (one batched UNION ALL scan, not a per-row
    query). Never raises — a DB error yields an empty Counter."""
    counts: Counter = Counter()
    try:
        with db.get_conn() as conn:
            rows = conn.execute(
                "SELECT title FROM inbox WHERE title != '' "
                "UNION ALL "
                "SELECT title FROM applications WHERE title != ''"
            ).fetchall()
    except Exception:
        return counts
    for r in rows:
        norm = _normalize_title(r["title"])
        if norm:
            counts[norm] += 1
    return counts


def _feed_cache_titles() -> list[str]:
    """Best-effort union of ``cached_titles()`` across the known single-feed
    clients. Each source is imported/constructed/read independently inside
    its own try/except so one broken or uninstantiable-offline source can't
    sink the others; a never-fetched (empty) cache just contributes nothing."""
    titles: list[str] = []
    for module_name, class_name in _FEED_CLIENTS:
        try:
            mod = importlib.import_module(module_name)
            cls = getattr(mod, class_name)
            client = cls()
            titles.extend(client.cached_titles())
        except Exception:
            continue
    return titles


def corpus_title_counts(*, min_count: int = 2, limit: int = 500) -> list[tuple[str, int]]:
    """The raw (title, count) frequency list from inbox+applications, for
    tests and for the API to preview. Pure read, no upsert, no feed-cache
    union (that's ``mine_corpus``'s job) — this is the SQL signal alone.
    Sorted by count desc, then title (case-insensitive) for a stable order."""
    counts = _sql_title_counts()
    ranked = sorted(
        (item for item in counts.items() if item[1] >= min_count),
        key=lambda item: (-item[1], item[0].lower()),
    )
    return ranked[:limit]


def mine_corpus(*, enabled: bool | None = None, limit: int = 200,
                min_count: int = 2) -> dict:
    """Derive candidate keywords from the user's OWN data and upsert them into
    the keyword pool as ``source='corpus'``.

    GATED: if ``enabled`` is None it reads ``cfg.get('discovery_enabled',
    False)`` via ``workspace.load_config()``; if that is False, returns
    ``{"mined": 0, "upserted": 0, "skipped": True, "reason": "disabled"}`` and
    does NOTHING (no DB scan, no cache read).

    When enabled:
      1. Batched SQL frequency scan of inbox.title + applications.title
         (normalized: strip + collapse whitespace).
      2. Best-effort feed-cache titles (union of ``cached_titles()`` across
         the known single-feed clients) added into the SAME frequency map —
         a feed-cache hit can push a borderline inbox title over
         ``min_count``, or stand on its own if it recurs across sources.
      3. Titles seen >= ``min_count`` (post-union) are upserted, top
         ``limit`` by frequency, as ``{"term", "tier": "adjacent",
         "source": "corpus", "status": "suggested"}``.

    Returns ``{"mined": <distinct titles considered>, "upserted": <new pool
    rows>, "skipped": False, "reason": ""}``. Never raises."""
    try:
        if enabled is None:
            try:
                cfg = workspace.load_config()
            except Exception:
                cfg = {}
            enabled = bool((cfg or {}).get("discovery_enabled", False))
        if not enabled:
            return {"mined": 0, "upserted": 0, "skipped": True, "reason": "disabled"}

        counts = _sql_title_counts()
        for title in _feed_cache_titles():
            norm = _normalize_title(title)
            if norm:
                counts[norm] += 1

        frequent = sorted(
            (item for item in counts.items() if item[1] >= min_count),
            key=lambda item: (-item[1], item[0].lower()),
        )
        top = frequent[:limit]

        try:
            upserted = pool.upsert_terms([
                {"term": t, "tier": "adjacent", "source": "corpus",
                 "status": "suggested"}
                for t, _ in top
            ])
        except Exception:
            upserted = 0

        return {"mined": len(counts), "upserted": upserted, "skipped": False,
                 "reason": ""}
    except Exception:
        return {"mined": 0, "upserted": 0, "skipped": True, "reason": "error"}
