"""Companies API — Add Companies, validate/build/seed employer lists (Phase 5).

Re-hosts the tk "Add Companies" dialog + "Build My List" + "Seed My Area" flows
over HTTP without importing Tk. The detect/validate/add split mirrors the tk
dialog: paste lines -> detect ATS per line (instant) -> validate live (probe each,
streamed as a job) -> add with tk's EXACT verified-by-default (P0-6) gating. The
list-build + metro-seed are long engine ops run as EXCLUSIVE jobs on the shared
:class:`~webui.jobs.JobRunner` (same mutex the daily run / search use — two engine
ingests never run concurrently in-process), streaming their line logs over the
existing SSE surface.

Engine seams (all Tk-free, imported directly):
* detect  — ``scrape.ats_detect.parse_line`` (one paste line -> CompanyEntry|None)
* probe   — ``scrape.ats_detect.probe_board`` (ProbeResult{count, reachable})
* save    — ``scrape.company_registry.save_companies`` (+ UNVERIFIED_FLAG gating)
* build   — ``build_company_list.build_company_list(log=sink, **opts)``
* seed    — ``discover.seed_metro.seed_my_metro(industry, metro, log=cb)`` (key-gated)
* prompt  — ``ui.ai_setup.build_seed_prompt`` / ``apply_seed_lines``

Routes (mounted under ``/api``)
-------------------------------
* ``POST /api/companies/detect``       {lines}                 -> candidates       [gate]
* ``POST /api/companies/validate``     {candidates}            -> job (probe each)  [gate]
* ``POST /api/companies/add``          {entries, keep_unreachable} -> save          [gate]
* ``POST /api/companies/build-list``   {opts}                  -> exclusive job     [gate]
* ``POST /api/companies/seed-metro``   {industry, metro}       -> exclusive job     [gate,
                                                                    409 if no key]
* ``GET  /api/companies/seed-prompt``  ?field=&metro=          -> copyable prompt   (read)
* ``POST /api/companies/seed-apply``   {text, industry?}       -> detect+probe+save [gate]
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

import workspace
from ..jobs import runner, JobConflict
from ..security import require_local_origin

companies_bp = Blueprint("webui_companies", __name__)


# ── detect (instant, per line) ────────────────────────────────────────────────
@companies_bp.post("/companies/detect")
@require_local_origin
def companies_detect():
    """Parse pasted ``Name | URL`` / bare-URL lines into ATS candidates WITHOUT any
    network (the instant feedback the tk dialog shows as you paste). Each line runs
    through ``ats_detect.parse_line`` (which drops prose lines with no URL — S35
    hardening). Body ``{lines: str | [str]}`` (a blob or a list). Returns ``{ok,
    candidates:[{line, name, ats, slug, status}]}`` where ``status`` is
    'detected' for a real ATS board, 'direct' for a raw careers page, or 'dropped'
    for a line that carried no URL (reported so the user sees what was skipped —
    inclusion over precision)."""
    from scrape.ats_detect import parse_line

    data = request.get_json(silent=True) or {}
    raw = data.get("lines")
    if isinstance(raw, list):
        lines = [str(x) for x in raw]
    else:
        lines = str(raw or "").splitlines()

    candidates = []
    for ln in lines:
        if not ln.strip():
            continue
        entry = parse_line(ln)
        if entry is None:
            candidates.append({"line": ln.strip(), "name": "", "ats": "",
                               "slug": "", "status": "dropped"})
            continue
        status = "direct" if entry.ats_type == "direct" else "detected"
        candidates.append({"line": ln.strip(), "name": entry.name,
                           "ats": entry.ats_type, "slug": entry.slug,
                           "status": status})
    return jsonify({"ok": True, "candidates": candidates})


# ── validate (live probe, as a job) ───────────────────────────────────────────
@companies_bp.post("/companies/validate")
@require_local_origin
def companies_validate():
    """Live-probe each candidate board on a background job, streaming a log line per
    board, and return per-board verdicts in the job result. Mirrors the tk dialog's
    "verify" step. Body ``{candidates:[{name, ats, slug}]}`` (the detect output, or
    a hand-built list). Returns ``{ok, job_id}``.

    The job result is ``{results:[{name, ats, slug, verdict, detail, count?}]}`` where
    ``verdict`` is:
    * ``live``        — the probe READ the board (count>=0; a 0-job board is
                        live-but-empty, still verified);
    * ``direct``      — a user-supplied raw careers page (uncountable, treated as
                        verified-manual, not probed);
    * ``unreachable`` — a dead/walled board (kept-unverified on add).

    NOT exclusive (a read-only probe touches no project state / engine globals), but
    single-flight per project so a double-submit can't fan out duplicate probe
    storms."""
    data = request.get_json(silent=True) or {}
    cands = data.get("candidates")
    if not isinstance(cands, list) or not cands:
        return jsonify({"ok": False, "error": "no candidates"}), 400

    # Snapshot the plain dicts now; the job thread rebuilds CompanyEntry from them
    # (never captures a request-scoped object).
    items = [{"name": str(c.get("name") or ""), "ats": str(c.get("ats") or ""),
              "slug": str(c.get("slug") or "")}
             for c in cands if isinstance(c, dict)]
    slug = workspace.active_slug()

    def _fn(handle):
        from scrape.ats_detect import probe_board, CompanyEntry
        results = []
        for it in items:
            if handle.cancelled.is_set():
                break
            name, ats, s = it["name"], it["ats"], it["slug"]
            entry = CompanyEntry(name=name, ats_type=ats, slug=s, industries=[])
            if ats == "direct":
                handle.log(f"{name or s}: direct careers page (kept as-is).")
                results.append({"name": name, "ats": ats, "slug": s,
                                "verdict": "direct",
                                "detail": "direct page (verified-manual)"})
                continue
            pr = probe_board(entry)
            if pr is not None and pr.reachable:
                n = pr.count if pr.count is not None else 0
                handle.log(f"{name or s}: live ({n} open jobs).")
                results.append({"name": name, "ats": ats, "slug": s,
                                "verdict": "live", "count": n,
                                "detail": f"live ({n} open jobs)"})
            else:
                handle.log(f"{name or s}: unreachable (walled or dead).")
                results.append({"name": name, "ats": ats, "slug": s,
                                "verdict": "unreachable",
                                "detail": "unreachable (kept unverified if added)"})
        handle.log(f"Validated {len(results)} board(s).")
        return {"results": results}

    try:
        job_id = runner.start("companies_validate", str(slug or ""), _fn)
    except JobConflict as jc:
        return jsonify({"ok": False, "error": "already running",
                        "job_id": jc.running_job_id}), 409
    return jsonify({"ok": True, "job_id": job_id})


# ── add (save with P0-6 verified-by-default gating) ───────────────────────────
@companies_bp.post("/companies/add")
@require_local_origin
def companies_add():
    """Save validated entries with tk's EXACT verified-by-default gate (P0-6). Body
    ``{entries:[{name, ats, slug, verdict, industry?}], keep_unreachable:bool}``.

    Gating (identical to the tk dialog / ``ai_setup.apply_seed_lines``):
    * ToS-blocked/aggregator hosts (NEOGOV, Indeed, LinkedIn, …) are REJECTED —
      never saved (critical: an AI-drivable path must not seed a ToS-gray target);
    * a ``live``/``direct`` verdict saves the board VERIFIED (scraped);
    * an ``unreachable`` verdict is saved marked UNVERIFIED (excluded from scraping
      until it re-verifies) ONLY when ``keep_unreachable`` is true; otherwise it is
      dropped. This is the tk "keep unreachable boards?" choice.

    Returns ``{ok, added, verified, unverified, rejected, dropped}``. Pins the
    active project across the write (S27-safe)."""
    from scrape.ats_detect import is_tos_blocked_host, CompanyEntry
    from scrape.company_registry import UNVERIFIED_FLAG, save_companies

    data = request.get_json(silent=True) or {}
    entries = data.get("entries")
    if not isinstance(entries, list) or not entries:
        return jsonify({"ok": False, "error": "no entries"}), 400
    keep_unreachable = bool(data.get("keep_unreachable", False))

    to_save = []
    verified = unverified = rejected = dropped = 0
    for e in entries:
        if not isinstance(e, dict):
            continue
        name = str(e.get("name") or "")
        ats = str(e.get("ats") or "")
        slug = str(e.get("slug") or "")
        verdict = str(e.get("verdict") or "").lower()
        industry = str(e.get("industry") or "").strip()
        if not slug:
            dropped += 1
            continue
        # ToS/aggregator guard — never save a blocked host regardless of verdict.
        if is_tos_blocked_host(slug):
            rejected += 1
            continue
        entry = CompanyEntry(name=name, ats_type=ats, slug=slug,
                             industries=[industry] if industry else [])
        if verdict in ("live", "direct"):
            verified += 1
            to_save.append(entry)
        elif verdict == "unreachable":
            if keep_unreachable:
                entry.extra = dict(getattr(entry, "extra", None) or {})
                entry.extra[UNVERIFIED_FLAG] = True
                unverified += 1
                to_save.append(entry)
            else:
                dropped += 1
        else:
            # Unknown/missing verdict: treat as unreachable-unless-kept (never
            # silently save an unvalidated board as verified).
            if keep_unreachable:
                entry.extra = dict(getattr(entry, "extra", None) or {})
                entry.extra[UNVERIFIED_FLAG] = True
                unverified += 1
                to_save.append(entry)
            else:
                dropped += 1

    slug = workspace.active_slug()
    workspace.pin_active(slug)
    try:
        added = save_companies(to_save) if to_save else 0
    finally:
        workspace.unpin_active()
    return jsonify({"ok": True, "added": added, "verified": verified,
                    "unverified": unverified, "rejected": rejected,
                    "dropped": dropped})


# ── build my list (exclusive engine job) ──────────────────────────────────────
@companies_bp.post("/companies/build-list")
@require_local_origin
def companies_build_list():
    """Build (or grow) the target-company list for the active project via
    ``build_company_list.build_company_list(log=handle.log, **opts)`` on an
    EXCLUSIVE engine job (it harvests the inbox + enumerates + seeds, touching the
    registry + engine globals — same mutex the daily run uses). Body ``{opts}``:
    all optional — ``{metro?, industry?, national?, dataset?, use_inbox?, jobhive?,
    seed_metro?, seed_limit?, classify?, dry_run?}`` (mirrors the CLI/tk flags).
    Returns ``{ok, job_id}``; the job result is the build summary dict.

    409 carries the running job's id: same project already building ->
    ``already running``; a DIFFERENT project's engine job in flight -> ``another
    run is in progress`` (the exclusive mutex). A ``ValueError`` from the engine
    (no field + no metro resolvable) surfaces as a failed job with its message."""
    data = request.get_json(silent=True) or {}
    opts = data.get("opts") if isinstance(data.get("opts"), dict) else data
    opts = opts if isinstance(opts, dict) else {}

    # Allowlist the safe engine kwargs (never forward an arbitrary key into the
    # builder). Booleans coerced; strings stripped-or-None.
    def _s(key):
        v = opts.get(key)
        v = str(v).strip() if v is not None else ""
        return v or None

    def _b(key, default=False):
        return bool(opts.get(key, default))

    seed_limit = opts.get("seed_limit")
    try:
        seed_limit = int(seed_limit) if seed_limit not in (None, "") else None
    except (TypeError, ValueError):
        seed_limit = None

    kw = dict(
        metro=_s("metro"), industry=_s("industry"), national=_b("national"),
        dataset=_s("dataset"), use_inbox=_b("use_inbox", True),
        jobhive=_b("jobhive"), seed_metro=_b("seed_metro"),
        seed_limit=seed_limit, classify=_b("classify"), dry_run=_b("dry_run"),
    )
    slug = workspace.active_slug()

    def _fn(handle):
        import build_company_list
        # The builder resolves field/metro from the ACTIVE project when not given;
        # pin the slug so a background switch can't repoint it (S27-safe).
        workspace.pin_active(slug)
        try:
            return build_company_list.build_company_list(
                project=slug or None, log=handle.log, **kw)
        finally:
            workspace.unpin_active()

    try:
        job_id = runner.start("build_list", str(slug or ""), _fn, exclusive=True)
    except JobConflict as jc:
        msg = ("already running" if jc.same_gate
               else "another run is in progress")
        return jsonify({"ok": False, "error": msg,
                        "job_id": jc.running_job_id}), 409
    return jsonify({"ok": True, "job_id": job_id})


# ── seed my area (key-gated exclusive job) ────────────────────────────────────
@companies_bp.post("/companies/seed-metro")
@require_local_origin
def companies_seed_metro():
    """Seed a VERIFIED local-employer registry from CareerOneStop Business Finder
    (``discover.seed_metro.seed_my_metro``) on an EXCLUSIVE engine job (it probes +
    saves boards). KEY-GATED: with no CareerOneStop key set, returns 409 ``{ok:false,
    error:<helpful>, need_key:true}`` up front (a keyless run would just no-op) —
    the helpful error names the two free secrets to add. Body ``{industry?, metro?,
    keyword?, limit?}`` (blank industry+metro fall back to the active project's
    config, resolved in the job). Returns ``{ok, job_id}``; the job result is the
    ``SeedResult.as_dict()`` summary."""
    from discover.business_finder import BusinessFinderClient

    # Up-front key gate (avoids spinning an exclusive job that can only no-op).
    if not BusinessFinderClient().has_key():
        return jsonify({
            "ok": False, "need_key": True,
            "error": ("No CareerOneStop key — add a free CAREERONESTOP_USER_ID + "
                      "CAREERONESTOP_TOKEN in Connect job sources to seed your "
                      "area."),
        }), 409

    data = request.get_json(silent=True) or {}
    cfg = {}
    try:
        cfg = workspace.load_config()
    except Exception:  # noqa: BLE001
        cfg = {}
    industry = str(data.get("industry") or cfg.get("industry") or "").strip()
    metro = str(data.get("metro") or cfg.get("location") or "").strip()
    keyword = str(data.get("keyword") or "").strip()
    try:
        limit = int(data.get("limit") or 0) or None
    except (TypeError, ValueError):
        limit = None

    slug = workspace.active_slug()

    def _fn(handle):
        from discover.seed_metro import seed_my_metro, DEFAULT_MAX_EMPLOYERS
        workspace.pin_active(slug)
        try:
            res = seed_my_metro(
                industry=industry, metro=metro, keyword=keyword,
                limit=limit or DEFAULT_MAX_EMPLOYERS, log=handle.log)
            return res.as_dict()
        finally:
            workspace.unpin_active()

    try:
        job_id = runner.start("seed_metro", str(slug or ""), _fn, exclusive=True)
    except JobConflict as jc:
        msg = ("already running" if jc.same_gate
               else "another run is in progress")
        return jsonify({"ok": False, "error": msg,
                        "job_id": jc.running_job_id}), 409
    return jsonify({"ok": True, "job_id": job_id})


# ── AI seed prompt / apply ────────────────────────────────────────────────────
@companies_bp.get("/companies/seed-prompt")
def companies_seed_prompt():
    """The copyable AI company-seeding prompt (``ai_setup.build_seed_prompt``) — asks
    the user's AI for ``Name | careers-page URL`` lines (careers pages, not slugs,
    per the persona evidence). READ-only. Query ``?field=&metro=&limit=`` (all
    optional; blank -> generic wording). Returns ``{ok, prompt}``."""
    from ui.ai_setup import build_seed_prompt
    field = str(request.args.get("field") or "").strip()
    metro = str(request.args.get("metro") or "").strip()
    try:
        limit = int(request.args.get("limit") or 30)
    except (TypeError, ValueError):
        limit = 30
    return jsonify({"ok": True,
                    "prompt": build_seed_prompt(field, metro, limit=limit)})


@companies_bp.post("/companies/seed-apply")
@require_local_origin
def companies_seed_apply():
    """Parse pasted ``Name | URL`` lines, detect/probe each, and save with the P0-6
    verified-by-default gate (``ai_setup.apply_seed_lines`` — the exact tk pipeline,
    incl. the ToS-host rejection + unverified-flag gating). Body ``{text,
    industry?}``. Returns ``{ok, result:{parsed, added, verified, unverified,
    skipped, rejected, verdicts:[...]}}``. Pins the active project across the save
    (S27-safe). NOTE: this probes each board live, so it can take a few seconds for
    a long list — kept synchronous to mirror the tk dialog (the async job path is
    /companies/validate + /companies/add)."""
    from ui.ai_setup import apply_seed_lines

    data = request.get_json(silent=True) or {}
    text = str(data.get("text") or "")
    industry = str(data.get("industry") or "").strip()
    if not text.strip():
        return jsonify({"ok": False, "error": "nothing pasted"}), 400

    slug = workspace.active_slug()
    workspace.pin_active(slug)
    try:
        result = apply_seed_lines(text, industry=industry)
    finally:
        workspace.unpin_active()
    return jsonify({"ok": True, "result": result})
