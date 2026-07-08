"""Tk-free core of the in-app multi-source Search (S36 web migration).

This is a faithful port of ``ui.tab_search.SearchTab._worker`` with the tkinter
marshalling removed: it builds the same clients (respecting the project's source
toggles / industry gate / keyword broadening), runs ``SearchEngine.run_full_search``
with a progress callback and a cancel Event, applies the SAME ``match.scorer.score_jobs``
call the tk tab makes (scoring PARITY — identical kwargs), hides already-seen rows,
and returns the scored ``JobResult`` list plus a per-source health list classified
through the shared ``ui.tab_search_core`` helpers.

The tk tab keeps its own ``_worker`` (unchanged) — this core is the seam the web
Search job wraps. Both call ``score_jobs`` the identical way; neither touches
``match/`` or the scorer's levers, so search scoring stays byte-identical.

``on_event`` (optional) receives the engine's progress dicts verbatim (phases
``start`` / ``source_start`` / ``source_done`` / ``done``) so the web job can wrap
each into an SSE JSON-line frame. ``cancel`` (optional threading.Event) is wired
straight into ``run_full_search`` — in-flight sources finish, no new work starts,
partial results are scored and returned (same as the tk Cancel button).
"""
from __future__ import annotations

import threading
from typing import Callable, Optional

from ui import tab_search_core as _core


def run_search(
    keywords: list[str],
    location: str,
    salary_min: Optional[int],
    *,
    user_cfg: dict,
    hide_tracked: bool = True,
    on_event: Optional[Callable[[dict], None]] = None,
    cancel: Optional[threading.Event] = None,
) -> tuple[list, list[dict]]:
    """Run the full multi-source search and return ``(results, health)``.

    ``results`` is the scored, deduped ``list[JobResult]`` (already hidden of
    tracked/dismissed rows when ``hide_tracked``). ``health`` is a list of per-source
    dicts ``{source, count, ok, error, skipped_keyless, status}`` — ``status`` is the
    single token (``ok``/``keyless``/``throttled``/``failed``) from
    ``tab_search_core.source_status``. Mirrors ``SearchTab._worker`` exactly.
    """
    from search.cli import build_clients, ALL_SOURCES
    from search.search_engine import SearchEngine
    from match.scorer import score_jobs
    from search.keyword_strategy import gate_tech_sources, broad_query_keywords
    from tracker.db import seen_urls, normalize_url

    user_cfg = user_cfg or {}
    cfg_sources = (user_cfg.get("sources") or {})
    industry = user_cfg.get("industry") or ""

    # Respect the user's source toggles like the CLI does, then drop
    # tech/remote-skewed boards for a non-knowledge-work field (no-op for eng).
    sources = [s for s in ALL_SOURCES if cfg_sources.get(s, True)]
    sources = gate_tech_sources(sources, industry, cfg_sources)

    # Collect sources that self-skipped for a missing free key this run so the
    # health classifier can tell that apart from a source that ran and found 0.
    skipped_keyless: list[str] = []
    clients = build_clients(
        sources, cache_enabled=True,
        industry_filter=industry or None,
        tiered_careers=True,
        location=location,
        skipped_keyless=skipped_keyless)

    # Broaden the QUERY keywords for API recall (search broad, score narrow); the
    # original `keywords` stay the scoring set. No-op for eng IC titles; opt out
    # with "broaden_keywords": false.
    if user_cfg.get("broaden_keywords", True):
        import industry_profile
        synonyms = industry_profile.resolve(industry).query_synonyms
        query_keywords = broad_query_keywords(keywords, industry, synonyms=synonyms)
    else:
        query_keywords = keywords

    # Per-source health rows are collected off the engine's progress events, then
    # ALSO forwarded to the caller's on_event (so the SSE console streams live).
    health: list[dict] = []

    def _progress(event: dict) -> None:
        if event.get("phase") == "source_done":
            src = event.get("source", "")
            skipped = _core.class_is_keyless_skipped(src, skipped_keyless)
            row = {
                "source": src,
                "count": event.get("count", 0),
                "ok": bool(event.get("ok", True)),
                "error": event.get("error", ""),
                "skipped_keyless": skipped,
            }
            row["status"] = _core.source_status(row)
            health.append(row)
        if on_event is not None:
            try:
                on_event(event)
            except Exception:  # noqa: BLE001 — a sink must never break the search
                pass

    if clients:
        engine = SearchEngine(clients)
        results = engine.run_full_search(
            keywords=query_keywords, location=location,
            salary_min=salary_min, max_pages_per_keyword=2,
            progress=_progress, cancel=cancel)
        # Persist tiering state so a tiered careers leg advances its board buckets
        # (mirrors daily_run / the tk tab).
        for c in clients:
            if hasattr(c, "finalize_tiering"):
                try:
                    c.finalize_tiering()
                except Exception:
                    pass
    else:
        results = []

    # Track which URLs are already seen (tracked/dismissed) BEFORE any hide, so the
    # serializer can flag `seen` even when hide_tracked is off (the tk 'Hide
    # tracked/dismissed' checkbox); computed once.
    seen = seen_urls() if results else set()
    if hide_tracked and results:
        results = [r for r in results if normalize_url(r.url) not in seen]

    if results:
        try:
            import preferences as _prefs
            _hard = _prefs.load().get("hard", {})
            remote_ok = bool(_hard.get("remote_ok", True))
            remote_regions_ok = bool(_hard.get("remote_regions_ok", False))
        except Exception:
            remote_ok = True
            remote_regions_ok = False
        # SCORING PARITY: identical kwargs to SearchTab._worker's score_jobs call.
        score_jobs(results, keywords=keywords, location=location,
                   salary_floor=salary_min,
                   exclude_keywords=user_cfg.get("exclude_keywords", []),
                   exclude_titles=user_cfg.get("exclude_titles"),
                   title_miss_penalty=user_cfg.get("title_miss_penalty"),
                   seniority_exclude=user_cfg.get("seniority_exclude"),
                   remote_ok=remote_ok,
                   seniority_target=user_cfg.get("seniority_target"),
                   years_cap=user_cfg.get("years_cap"),
                   remote_regions_ok=remote_regions_ok,
                   title_context_required=user_cfg.get("title_context_required"),
                   suggested_excludes=user_cfg.get("suggested_excludes"))

    return results, health


def seen_for_urls(urls) -> set[str]:
    """The subset of ``urls`` that are already tracked/dismissed (normalized), for
    the serializer's ``seen`` flag. Thin wrapper so the API doesn't import
    tracker.db directly for this."""
    from tracker.db import seen_urls, normalize_url
    seen = seen_urls()
    return {u for u in urls if normalize_url(u) in seen}
