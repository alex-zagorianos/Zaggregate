"""Search Discovery API — the keyword-pool subsystem over HTTP (search-discovery
plan §4.4).

Surfaces the offline suggestion engine, the live yield probe, corpus mining, and
the pool CRUD so the web Discovery panel (and, via the same core, the Tk dialog)
can turn a free-typed field into a rich, reviewable keyword set. The heavy lifting
lives in the Tk-free ``search.discovery`` package; these routes are thin adapters.

Contract preserved everywhere: ``cfg['keywords']`` stays the single source of
truth for what is searched. Activating a pool term MIRRORS it into
``cfg['keywords']``; deactivating removes it. Nothing here drops a job.

Routes (mounted under ``/api``)
-------------------------------
* ``GET  /discovery/propose``            -> offline tiers for a field/résumé      (read)
* ``GET  /discovery/keywords``           -> typeahead over the O*NET vocabulary    (read)
* ``GET  /discovery/pool``               -> current keyword_pool for this project  (read)
* ``POST /discovery/probe``              -> live Adzuna yield check (budget 10/day) [gate]
* ``POST /discovery/mine``               -> corpus-mine the user's own data        [gate]
* ``POST /discovery/levels``             -> experience-level phrasing variants     [gate]
* ``POST /discovery/keywords/activate``  -> suggestion -> active (+cfg['keywords']) [gate]
* ``POST /discovery/keywords/deactivate``-> active -> inactive (-cfg['keywords'])   [gate]
* ``POST /discovery/excludes``           -> add/remove a suggested-exclude term    [gate]

Security: every mutating route is ``@require_local_origin`` (the same convention
the meta-test enumerates over ``app.url_map``). No secret ever leaves the server.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

import workspace
from search.discovery import flag, levels, mine, pool, probe, propose
from ..security import require_local_origin

discovery_bp = Blueprint("webui_discovery", __name__)


def _persist_suggestions(result: dict) -> None:
    """Upsert every proposed term into the pool as a tracked suggestion so the
    pool view + activate flow have rows to act on. Never raises."""
    rows = []
    for tier in ("core", "adjacent", "exploratory"):
        for item in result.get(tier) or []:
            term = (item.get("term") or "").strip()
            if term:
                rows.append({"term": term, "tier": tier,
                             "source": item.get("source") or "onet",
                             "status": "suggested"})
    if rows:
        try:
            pool.upsert_terms(rows)
        except Exception:  # noqa: BLE001 — persistence is best-effort for a read
            pass


# ── reads (ungated) ────────────────────────────────────────────────────────────
@discovery_bp.get("/discovery/propose")
def discovery_propose():
    """Offline suggestion tiers for a free-typed ``field`` (optional ``resume``
    text helps resolve a blank field). READ-only, zero network, works on a cold
    install. Side-effect: the proposals are upserted into the pool as suggestions
    (idempotent) so the panel and activate flow are stateful — a read that seeds
    its own working set, never a scoring mutation. Returns the tiers dict."""
    field = str(request.args.get("field") or "").strip()
    resume = str(request.args.get("resume") or "")
    result = propose.propose(field, resume_text=resume)
    _persist_suggestions(result)
    return jsonify({"ok": True, **result})


@discovery_bp.get("/discovery/keywords")
def discovery_keywords():
    """Typeahead over the field/title vocabulary (exact + prefix, never fuzzy).
    Query ``q`` (blank -> []), ``limit`` (default 20). READ-only."""
    q = str(request.args.get("q") or "")
    try:
        limit = int(request.args.get("limit", 20))
    except (TypeError, ValueError):
        limit = 20
    return jsonify({"ok": True, "suggestions": propose.keyword_suggest(q, limit=limit)})


@discovery_bp.get("/discovery/pool")
def discovery_pool():
    """The current keyword_pool for the active project, optionally filtered by
    ``status`` / ``tier``. Also returns the low-activity nudges (never mutating).
    READ-only."""
    status = request.args.get("status") or None
    tier = request.args.get("tier") or None
    return jsonify({"ok": True,
                    "pool": pool.get_pool(status=status, tier=tier),
                    "low_activity": flag.low_activity_terms()})


# ── mutations (origin-gated) ────────────────────────────────────────────────────
@discovery_bp.post("/discovery/probe")
@require_local_origin
def discovery_probe():
    """Live "openings nearby" yield for a small list of terms — ONE cheap Adzuna
    page-1 call each, capped at 10/day per project (shared limiter, never
    additive to the daily run). Body ``{terms:[...], location?}``. Returns one
    result per term (skipped ones carry a reason)."""
    data = request.get_json(silent=True) or {}
    terms = [str(t).strip() for t in (data.get("terms") or []) if str(t).strip()]
    location = str(data.get("location") or "").strip()
    if not terms:
        return jsonify({"ok": True, "results": [],
                        "probes_remaining_today": probe.probes_remaining()})
    results = probe.probe_terms(terms, location)
    return jsonify({"ok": True, "results": results,
                    "probes_remaining_today": probe.probes_remaining()})


@discovery_bp.post("/discovery/mine")
@require_local_origin
def discovery_mine():
    """Corpus-mine the user's OWN data (inbox history + already-fetched feed
    caches) into the pool as ``source='corpus'`` suggestions. This is an explicit
    user action, so it runs regardless of the cfg gate; it ALSO flips
    ``cfg['discovery_enabled']`` True so future daily runs may refresh the corpus.
    Returns the mine summary. Body: none required."""
    slug = workspace.active_slug()
    workspace.pin_active(slug)
    try:
        cfg = workspace.load_config()
        if not cfg.get("discovery_enabled"):
            cfg["discovery_enabled"] = True
            workspace.save_config(cfg)
        summary = mine.mine_corpus(enabled=True)
    finally:
        workspace.unpin_active()
    return jsonify({"ok": True, **summary})


@discovery_bp.post("/discovery/levels")
@require_local_origin
def discovery_levels():
    """Experience-level phrasing variants for the given (or current) core terms.
    entry/mid produce junior/associate/"I"-style variants; senior/manager/exec
    produce NONE (recall-collapse guard). Variants are upserted as suggestions.
    Body ``{level, terms?}`` (terms default to cfg['keywords']). Returns them."""
    data = request.get_json(silent=True) or {}
    level = str(data.get("level") or "").strip()
    terms = [str(t).strip() for t in (data.get("terms") or []) if str(t).strip()]
    if not terms:
        terms = list(workspace.load_config().get("keywords") or [])
    variants = levels.level_query_variants(terms, level)
    if variants:
        pool.upsert_terms(variants)
    return jsonify({"ok": True, "variants": variants})


@discovery_bp.post("/discovery/keywords/activate")
@require_local_origin
def discovery_activate():
    """Activate a suggestion: mark the pool row ``active`` and MIRROR the term into
    ``cfg['keywords']`` (the search source of truth). Upserts the term first if it
    isn't in the pool yet (a manually typed one). Activating anything also flips
    ``cfg['discovery_enabled']`` True. Body ``{term, tier?, source?}``. Returns the
    updated active keyword list."""
    data = request.get_json(silent=True) or {}
    term = str(data.get("term") or "").strip()
    if not term:
        return jsonify({"ok": False, "error": "term is required"}), 400
    tier = str(data.get("tier") or "core").strip() or "core"
    source = str(data.get("source") or "manual").strip() or "manual"

    slug = workspace.active_slug()
    workspace.pin_active(slug)
    try:
        pool.upsert_terms([{"term": term, "tier": tier, "source": source,
                            "status": "suggested"}])
        pool.set_status(term, "active")
        cfg = workspace.load_config()
        kws = list(cfg.get("keywords") or [])
        if term not in kws:
            kws.append(term)
        cfg["keywords"] = kws
        cfg["discovery_enabled"] = True
        workspace.save_config(cfg)
    finally:
        workspace.unpin_active()
    return jsonify({"ok": True, "keywords": kws})


@discovery_bp.post("/discovery/keywords/deactivate")
@require_local_origin
def discovery_deactivate():
    """Deactivate a term: mark the pool row ``inactive`` and REMOVE it from
    ``cfg['keywords']``. Body ``{term}``. Returns the updated active keyword list.
    Never drops anything from the inbox — it just stops searching that term."""
    data = request.get_json(silent=True) or {}
    term = str(data.get("term") or "").strip()
    if not term:
        return jsonify({"ok": False, "error": "term is required"}), 400

    slug = workspace.active_slug()
    workspace.pin_active(slug)
    try:
        pool.set_status(term, "inactive")
        cfg = workspace.load_config()
        kws = [k for k in (cfg.get("keywords") or []) if k != term]
        cfg["keywords"] = kws
        workspace.save_config(cfg)
    finally:
        workspace.unpin_active()
    return jsonify({"ok": True, "keywords": kws})


@discovery_bp.post("/discovery/excludes")
@require_local_origin
def discovery_excludes():
    """Add or remove a user-confirmed suggested-exclude term. These feed the
    scorer's DOWNRANK-only lever (``cfg['suggested_excludes']``), NEVER gate.py's
    hard-drop. Body ``{term, action: 'add'|'remove'}``. Returns the updated list.
    """
    data = request.get_json(silent=True) or {}
    term = str(data.get("term") or "").strip()
    action = str(data.get("action") or "add").strip().lower()
    if not term:
        return jsonify({"ok": False, "error": "term is required"}), 400

    slug = workspace.active_slug()
    workspace.pin_active(slug)
    try:
        cfg = workspace.load_config()
        excludes = list(cfg.get("suggested_excludes") or [])
        if action == "remove":
            excludes = [e for e in excludes if e != term]
        elif term not in excludes:
            excludes.append(term)
        cfg["suggested_excludes"] = excludes
        workspace.save_config(cfg)
    finally:
        workspace.unpin_active()
    return jsonify({"ok": True, "suggested_excludes": excludes})
