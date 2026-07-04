"""Search API — multi-source search as a streaming job + result mutations (Phase 4).

Re-hosts the tk ``SearchTab`` over HTTP without importing Tk. The heavy search runs
on the shared :class:`~webui.jobs.JobRunner` as an EXCLUSIVE engine job (same mutex
the daily run uses — two engine ingests can't run concurrently in-process), wrapping
the Tk-free ``search.search_job.run_search`` core. Progress streams over the existing
SSE surface (``GET /api/jobs/<id>/events``); the final result (``GET /api/jobs/<id>``)
carries the serialized scored rows + per-source health.

SSE line-frame contract
-----------------------
The search job writes to ``handle.log`` (plain strings), which the SSE route emits
as ``event: line\\ndata: <text>\\n\\n``. To let ONE console distinguish structured
engine progress from plain human lines, structured frames are prefixed:

    @event {"phase":"start","total":8}
    @event {"phase":"source_start","source":"AdzunaClient"}
    @event {"phase":"source_done","source":"AdzunaClient","count":12,"ok":true,
            "error":"","done":1,"total":8}
    @event {"phase":"done","raw":140,"deduped":95}

i.e. the literal prefix ``@event `` followed by a single-line JSON object (the exact
dict the engine emitted). Any log line WITHOUT that prefix is a plain human status
line (e.g. the final "N result(s)." summary). The frontend RunConsole parses a line
by stripping ``@event `` and ``JSON.parse``-ing the remainder; a parse failure or a
missing prefix means "render as plain text". ``EVENT_PREFIX`` is the single source of
truth for the sentinel.

Routes (mounted under ``/api``)
-------------------------------
* ``POST /api/search``            start the search job (exclusive) -> ``{job_id}``  [gate]
* ``POST /api/search/track``      Track one result row -> tracker              [gate]
* ``POST /api/search/dismiss``    Dismiss a URL (hidden from future searches)  [gate]
* ``POST /api/search/add-all``    Add rows to the Inbox (tk per-company cap)   [gate]

Cancel reuses the existing ``POST /api/jobs/<id>/cancel`` (the job wires the Event
into ``run_full_search``); status/SSE reuse ``GET /api/jobs/<id>[/events]``.
"""
from __future__ import annotations

import json

from flask import Blueprint, jsonify, request

import workspace
from ..jobs import runner, JobConflict
from ..security import require_local_origin
from ..serializers import job_result as _ser_job, job_result_from_row

search_bp = Blueprint("webui_search", __name__)

# The sentinel that marks a structured progress frame inside the job log stream.
# A log line starting with this is ``@event `` + one JSON object; anything else is
# a plain human line. Kept here as the ONE definition both the job writer and any
# test assert against.
EVENT_PREFIX = "@event "


def _frame_event(event: dict) -> str:
    """Wrap an engine progress dict into a single log-line frame the SSE console
    can parse: ``@event {json}``. JSON is compact + single-line (no embedded
    newlines) so it survives the line-oriented SSE ``data:`` framing intact."""
    return EVENT_PREFIX + json.dumps(event, separators=(",", ":"), default=str)


def _load_user_cfg() -> dict:
    """The active project's user config (keywords/location/salary/sources/industry
    /scoring levers), via the same seam the tk tab uses. Late import keeps the
    module importable in a stripped checkout."""
    from search.cli import load_user_config
    return load_user_config()


# ── the search job ────────────────────────────────────────────────────────────
@search_bp.post("/search")
@require_local_origin
def start_search():
    """Start a multi-source search on a background EXCLUSIVE engine job for the
    active project. Body (all optional): ``{keywords?:[str]|str, location?:str,
    min_salary?:int, save?:bool}``. Missing fields fall back to the project config
    (mirrors the tk tab pre-filling from ``load_user_config``). ``save:true``
    persists keywords/location/salary to the project config exactly as the tk Save
    button does (``workspace.save_config``), BEFORE the search runs.

    Returns ``{ok, job_id}``. Conflicts are 409 carrying the running job's id:
    the SAME project already searching/ingesting -> ``already running``; a DIFFERENT
    project's engine job in flight -> ``another run is in progress`` (the exclusive
    engine mutex). 400 when no keywords can be resolved (neither body nor config).
    """
    data = request.get_json(silent=True) or {}
    cfg = _load_user_cfg()

    # Keywords: accept a list or a comma-joined string; fall back to config.
    raw_kw = data.get("keywords")
    if isinstance(raw_kw, str):
        keywords = [k.strip() for k in raw_kw.split(",") if k.strip()]
    elif isinstance(raw_kw, list):
        keywords = [str(k).strip() for k in raw_kw if str(k).strip()]
    else:
        keywords = [str(k).strip() for k in (cfg.get("keywords") or []) if str(k).strip()]
    if not keywords:
        return jsonify({"ok": False,
                        "error": "no keywords — enter at least one keyword"}), 400

    from config import DEFAULT_LOCATION
    location = (str(data.get("location") or "").strip()
                or (cfg.get("location") or "").strip() or DEFAULT_LOCATION)

    # min_salary: body wins; else config salary_min; a bad value -> None (no floor).
    if "min_salary" in data:
        try:
            min_salary = int(data["min_salary"]) or None
        except (TypeError, ValueError):
            min_salary = None
    else:
        try:
            min_salary = int(cfg.get("salary_min") or 0) or None
        except (TypeError, ValueError):
            min_salary = None

    hide_tracked = bool(data.get("hide_tracked", True))

    # Save?: persist keyword/location/salary to the project config exactly as the
    # tk Save button does (only non-empty fields; salary cleared when falsy).
    if data.get("save"):
        _persist_search_defaults(keywords, location, min_salary)

    slug = workspace.active_slug()

    def _fn(handle):
        def _on_event(event):
            # Structured engine progress -> a framed log line (SSE console parses).
            handle.log(_frame_event(event))

        from search import search_job
        results, health = search_job.run_search(
            keywords, location, min_salary,
            user_cfg=cfg, hide_tracked=hide_tracked,
            on_event=_on_event, cancel=handle.cancelled)

        # A plain human summary line (no @event prefix) closes the console, matching
        # the tk status line.
        if not results:
            handle.log("No results. Try broader keywords or a different location.")
        else:
            handle.log(f"{len(results)} result(s).")

        # Badge already tracked/dismissed rows (the tk 'Hide tracked/dismissed'
        # signal) even when hide_tracked was off. `seen_for_urls` returns the subset
        # of the passed URLs whose NORMALIZED form is already seen, so membership is
        # tested against the raw url the row carries.
        seen = search_job.seen_for_urls([r.url for r in results])
        rows = [_ser_job(r, seen=(r.url in seen)) for r in results]
        return {"rows": rows, "health": health}

    try:
        job_id = runner.start("search", str(slug or ""), _fn, exclusive=True)
    except JobConflict as jc:
        msg = ("already running" if jc.same_gate
               else "another run is in progress")
        return jsonify({"ok": False, "error": msg,
                        "job_id": jc.running_job_id}), 409
    return jsonify({"ok": True, "job_id": job_id})


def _persist_search_defaults(keywords: list[str], location: str,
                             salary_min: int | None) -> None:
    """Persist keyword/location/salary to the active project config — byte-for-byte
    the tk ``SearchTab._save_searches`` mutation (only non-empty keywords/location
    saved; salary_min set when truthy, else the key is removed)."""
    cfg = workspace.load_config()
    if keywords:
        cfg["keywords"] = keywords
    elif "keywords" in cfg:
        del cfg["keywords"]
    if location:
        cfg["location"] = location
    if salary_min:
        cfg["salary_min"] = salary_min
    elif "salary_min" in cfg:
        del cfg["salary_min"]
    workspace.save_config(cfg)


# ── result mutations ──────────────────────────────────────────────────────────
@search_bp.post("/search/track")
@require_local_origin
def track():
    """Track one search-result row as 'interested' (mirrors the tk Track button,
    which routes through ``tracker.service.track_search_results`` — the dup-guard
    lives there). ``track_search_results`` takes a LIST, so the single ``{row}`` is
    wrapped in a one-element list, exactly as the tk multi-select would pass it.
    Returns ``{ok, added, skipped}`` (added/skipped from the service's dup-guard).
    400 for a missing/blank row."""
    data = request.get_json(silent=True) or {}
    row = data.get("row")
    if not isinstance(row, dict) or not (row.get("url") or row.get("title")):
        return jsonify({"ok": False, "error": "missing row"}), 400
    from tracker import service
    job = job_result_from_row(row)
    added, skipped = service.track_search_results([job])
    return jsonify({"ok": True, "added": added, "skipped": skipped})


@search_bp.post("/search/dismiss")
@require_local_origin
def dismiss():
    """Dismiss a search result by URL — hidden from future searches (mirrors the tk
    Dismiss button -> ``tracker.service.dismiss_url``, which takes just the URL, so
    no JobResult reconstruction is needed). Body ``{url}``. Returns ``{ok}``. 400
    for a blank url."""
    data = request.get_json(silent=True) or {}
    url = str(data.get("url") or "").strip()
    if not url:
        return jsonify({"ok": False, "error": "missing url"}), 400
    from tracker import service
    service.dismiss_url(url)
    return jsonify({"ok": True})


@search_bp.post("/search/add-all")
@require_local_origin
def add_all():
    """Add search-result rows to the Inbox for triage (mirrors the tk 'Add all to
    Inbox' button). Reconstructs each row into a ``JobResult`` and calls
    ``tracker.db.inbox_add_many`` with the project's ``max_per_company`` cap —
    byte-for-byte how the tk tab calls it (``per_company_cap=cap`` only; no
    ``new_batch``). Pins the active project across the write (S27-safe) so a
    background project switch can't misroute it. Body ``{rows:[...]}``. Returns
    ``{ok, added}``. 400 for an empty/invalid rows list."""
    data = request.get_json(silent=True) or {}
    rows = data.get("rows")
    if not isinstance(rows, list) or not rows:
        return jsonify({"ok": False, "error": "no rows"}), 400
    jobs = [job_result_from_row(r) for r in rows if isinstance(r, dict)]
    if not jobs:
        return jsonify({"ok": False, "error": "no rows"}), 400

    cfg = _load_user_cfg()
    try:
        cap = int(cfg.get("max_per_company", 15) or 0)
    except (TypeError, ValueError):
        cap = 0

    from tracker.db import inbox_add_many
    slug = workspace.active_slug()
    workspace.pin_active(slug)  # pin BEFORE the db write (S27-safe)
    try:
        added = inbox_add_many(jobs, per_company_cap=cap)
    finally:
        workspace.unpin_active()
    return jsonify({"ok": True, "added": added})
