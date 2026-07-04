"""Inbox API — the flagship triage surface (Phase 3).

Re-hosts the tk InboxTab over HTTP without importing Tk. Everything here goes
through the engine seams (``tracker.service`` / ``tracker.db`` / ``rerank`` /
``coverage`` / ``applog`` / ``demo_data`` / ``workspace``) — no hand-rolled SQL —
and the read filters are the Tk-free port in ``webui.inbox_filters``, which mirrors
``InboxTab._filtered`` semantics exactly (inclusion over precision: filters are VIEW
filters, never a delete; dismiss/track are the only drop mechanisms).

Routes
------
GET  /api/inbox                     list + server-side filters + badges + computed fields
GET  /api/inbox/<id>/detail         fit-why / score breakdown / ghost / ats / preview
POST /api/inbox/dismiss-bulk        bulk dismiss (+ undo token), gated
POST /api/inbox/undo-dismiss        restore the last-dismissed batch, gated
POST /api/inbox/<id>/fit            set a single row's fit/why, gated
POST /api/inbox/undo-rerank         revert the last AI re-rank (any route), gated
POST /api/inbox/export              write the AI round-trip files -> download urls, gated
GET  /api/inbox/export/download/<name>   send_file, locked to the export dir
POST /api/inbox/import              apply an AI-returned CSV/JSON (file or paste), gated
POST /api/inbox/score-reply         clipboard-bridge paste -> score inbox rows, gated

The single mutating drop mechanism is dismiss (there is NO delete route — mirrors
the migration plan). Bulk dismiss stashes the dismissed rows server-side so
undo-dismiss can re-insert them, mirroring the tk ``_remember_undo`` / Undo button.
"""
from __future__ import annotations

import threading
from pathlib import Path

from flask import Blueprint, jsonify, request, send_file

import workspace
from config import DEFAULT_LOCATION
from geo.filter import DEFAULT_LOCATION_MODE
from match import ats_hint as atshintmod
from match import ghost as ghostmod
from match.scorer import score_breakdown, extract_skill_terms
from tracker import db
from tracker import service
from rerank.export import export_inbox
from rerank.import_ import import_scores

from ..security import require_local_origin
from ..serializers import inbox_row as _ser_inbox_row
from ..serializers import inbox_row_list as _ser_inbox_row_list
from .. import inbox_filters

inbox_bp = Blueprint("webui_inbox", __name__)


# ── undo-dismiss buffer ───────────────────────────────────────────────────────
# The last bulk-dismissed batch, keyed by an opaque token, so undo-dismiss can
# re-insert exactly those rows (mirrors the tk Undo button's ``self._undo_rows``).
# Process-local, single-slot per token; a bounded dict so a long session can't
# grow it unbounded. The token is returned to the client and echoed back on undo.
import uuid as _uuid
from collections import OrderedDict

_UNDO_MAX = 32
_undo_batches: "OrderedDict[str, list[dict]]" = OrderedDict()
_undo_lock = threading.Lock()


def _stash_undo(rows: list[dict]) -> str | None:
    """Remember a dismissed batch under a fresh token; return the token (or None
    for an empty batch). Evicts the oldest when the buffer is full."""
    if not rows:
        return None
    token = _uuid.uuid4().hex
    with _undo_lock:
        _undo_batches[token] = list(rows)
        while len(_undo_batches) > _UNDO_MAX:
            _undo_batches.popitem(last=False)
    return token


def _pop_undo(token: str | None) -> list[dict]:
    """Take (and remove) a stashed batch. ``token=None`` pops the most recent
    batch (mirrors the tk single-slot Undo, which has no token). Empty if none."""
    with _undo_lock:
        if token:
            return _undo_batches.pop(token, [])
        if not _undo_batches:
            return []
        _key, rows = _undo_batches.popitem(last=True)
        return rows


# ── home-metro resolution (Tk-free port of InboxTab._resolve_home) ────────────
def _resolve_home() -> dict:
    """Agnostic home metro + remote policy + pay floor for the Location/pay-floor
    view filters. Faithful port of ``InboxTab._resolve_home``: the active project's
    configured location, else the first preferences location, else the global
    default; remote-ok and salary floor from preferences/config. Never raises."""
    cfg = workspace.load_config()
    area = (cfg.get("location") or "").strip()
    remote_ok = True
    floor = None
    try:
        import preferences
        hard = preferences.load().get("hard", {})
        if not area and hard.get("locations"):
            area = str(hard["locations"][0]).strip()
        remote_ok = bool(hard.get("remote_ok", True))
        floor = hard.get("salary_min")
    except Exception:
        pass
    if not floor:
        floor = cfg.get("salary_min")
    home_area = area or DEFAULT_LOCATION
    # A remote-only home ('Remote', 'Anywhere', 'Remote - US', ...) is NOT a real
    # metro to key a local-focus filter on: metro_variants('Remote') resolves to
    # {'remote'}, which then substring-matches the word 'remote' inside almost
    # every row's location and mislabels the whole search as 'local' — while
    # DROPPING the one genuinely-remote row whose location text lacks that word.
    # Treat remote-only like "no home metro" so both local-focus modes short-circuit
    # to All-locations (the contract the frontend already assumes). (scenario #4)
    try:
        from search.remote_intent import is_remote_only
        _remote_only = is_remote_only(home_area)
    except Exception:
        _remote_only = False
    has_home = bool((home_area or "").strip()) and not _remote_only
    try:
        pay_floor = int(floor) if floor else None
    except (TypeError, ValueError):
        pay_floor = None
    return {"home_area": home_area, "has_home": has_home,
            "remote_ok": remote_ok, "pay_floor": pay_floor}


# ── sample inbox (tk parity: InboxTab.refresh L459-473) ───────────────────────
def _inbox_snapshot() -> list[dict]:
    """The Inbox row snapshot the read routes work over: the real inbox, OR — for a
    brand-new user whose real inbox is genuinely empty and who hasn't retired the
    demo yet — the bundled sample rows (``demo_data.demo_inbox_rows``).

    Faithful port of ``InboxTab.refresh``: a first-run empty inbox shows ~20
    pre-scored DEMO rows so the aha (a scored, location-clean, Score-vs-Fit inbox)
    lands before any source is connected. Read-only by construction — demo rows carry
    ``is_demo`` + negative ids and never touch the DB, so the mutating routes
    (dismiss/track/export) already no-op/404/skip them (dismiss & dismiss-bulk gate on
    ``db.inbox_all`` membership, track 404s on a missing DB row, export drops
    ``is_demo``). Retirement (the marker write) is owned by the tk app / daily run, not
    this GET route; ``should_show_demo`` already suppresses the demo the instant a real
    inbox exists (``inbox_count > 0``), so a read route never needs to write state.
    Best-effort: any failure falls back to the (empty) real inbox."""
    rows = list(db.inbox_all())
    if rows:
        return rows
    try:
        import config
        import demo_data
        if demo_data.should_show_demo(config.USER_DATA_DIR, len(rows)):
            return demo_data.demo_inbox_rows()
    except Exception:
        pass
    return rows


# ── query-param coercion ──────────────────────────────────────────────────────
def _int_arg(name: str):
    raw = (request.args.get(name) or "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _bool_arg(name: str) -> bool:
    return (request.args.get(name) or "").strip().lower() in ("1", "true", "yes", "on")


def _csv_arg(name: str) -> list[str]:
    raw = request.args.get(name) or ""
    return [p.strip() for p in raw.split(",") if p.strip()]


# ── computed row fields ───────────────────────────────────────────────────────
def _computed(row: dict, *, latest_batch, home: dict, mode: str) -> dict:
    """Cheap per-row fields the table needs, mirroring what the tk render computes:
    ``is_new`` (in the latest fresh batch), ``size`` (S/M/L/XL/? from board_count),
    ``location_visible`` (verdict under the requested Location mode)."""
    from geo.filter import location_visible
    board_count = row.get("board_count", -1)
    is_new = inbox_filters._is_new_row(row, latest_batch) if latest_batch else False
    # Location verdict under the requested mode. "All locations" / no home metro =>
    # always visible (never silently hide), matching the filter's own short-circuit.
    if mode and mode != "All locations" and home["has_home"]:
        loc_visible = location_visible(
            row.get("location") or "", row.get("title") or "",
            home["home_area"], mode, remote_ok=home["remote_ok"])
    else:
        loc_visible = True
    return {"is_new": bool(is_new),
            "size": inbox_filters.size_letter(board_count),
            "location_visible": bool(loc_visible)}


def _badges() -> dict:
    """The header badges the tk InboxTab shows: last-run summary (incl. the
    keyless-skipped count), the reach line, and the demo flag. Each piece is
    best-effort — a failure in one never blanks the whole response."""
    slug = workspace.active_slug()
    last_run = None
    try:
        import applog
        info = applog.last_run_info(slug) or {}
        if info:
            last_run = {
                "timestamp": info.get("timestamp"),
                "added": info.get("added", 0),
                "keyless_skipped": list(info.get("keyless_skipped") or []),
                # US-only sources skipped because this project's country isn't 'us'
                # — a distinct badge from keyless (not fixable by adding a key), so
                # the web UI can honestly report the country gate. (finding #3)
                "country_skipped": list(info.get("country_skipped") or []),
            }
    except Exception:
        last_run = None
    reach = None
    try:
        from coverage.reach import badge_line, badge_reason, load_latest
        snap = load_latest(slug or "root")
        line = badge_line(snap)
        reach = {"line": line, "reason": badge_reason(snap)} if line else None
    except Exception:
        reach = None
    demo = False
    try:
        import config
        import demo_data
        demo = bool(demo_data.should_show_demo(config.USER_DATA_DIR, db.inbox_count()))
    except Exception:
        demo = False
    return {"last_run": last_run, "reach": reach, "demo": demo}


# ── GET /api/inbox ────────────────────────────────────────────────────────────
@inbox_bp.get("/inbox")
def list_inbox():
    """Filtered inbox rows + badges. Query params (all optional, all VIEW filters):
    ``min_score``, ``sources`` (csv), ``size`` (S/M/L/XL/?), ``location_mode``,
    ``pay_floor`` (bool — applies the resolved preference floor), ``q``,
    ``new_only``, ``unscored_only``, ``hide_stale``, ``order`` (roundrobin|score),
    ``limit``, ``offset``.

    Response ``{ok, rows, total, shown, badges}`` — ``total`` is the pre-filter
    row count, ``shown`` is the count after filters (before limit/offset paging).
    ``pay_floor`` is a boolean toggle (like the tk "Meets pay floor" checkbox); the
    numeric floor comes from the project's preferences, never the client, so the
    client can't widen it.
    """
    order = (request.args.get("order") or "roundrobin").strip()
    if order not in ("roundrobin", "score"):
        order = "roundrobin"
    all_rows = list(db.inbox_all(order=order))
    # First-run onboarding parity with the tk InboxTab: an empty real inbox falls
    # back to the bundled sample rows (kept in their curated file order; the ``order``
    # sort only governs the real DB query). filter_rows() bypasses all view filters
    # while the whole set is demo, so the sample is never whittled down.
    if not all_rows:
        all_rows = _inbox_snapshot()
    total = len(all_rows)

    home = _resolve_home()
    mode = (request.args.get("location_mode") or "").strip() or None
    # With no home metro a local-focus mode has nothing to key on; the filter
    # short-circuits to "All locations" internally (has_home=False), so we never
    # empty the view.
    pay_floor = home["pay_floor"] if _bool_arg("pay_floor") else None

    filtered = inbox_filters.filter_rows(
        all_rows,
        min_score=_int_arg("min_score"),
        sources=_csv_arg("sources"),
        size=(request.args.get("size") or "").strip() or None,
        unscored_only=_bool_arg("unscored_only"),
        new_only=_bool_arg("new_only"),
        hide_stale=_bool_arg("hide_stale"),
        pay_floor=pay_floor,
        location_mode=mode,
        home_area=home["home_area"],
        has_home=home["has_home"],
        remote_ok=home["remote_ok"],
        q=request.args.get("q"),
        all_rows=all_rows,
    )
    shown = len(filtered)

    # Paging AFTER filtering (offset/limit over the filtered view).
    offset = _int_arg("offset") or 0
    if offset < 0:
        offset = 0
    limit = _int_arg("limit")
    page = filtered[offset:] if limit is None else filtered[offset:offset + max(0, limit)]

    latest_batch = inbox_filters._latest_new_batch(all_rows)
    rows_out = []
    for r in page:
        # List context: no description preview is rendered here (the detail route
        # below carries the full field + its own preview), so drop it to cut
        # payload size.
        ser = _ser_inbox_row_list(r)
        ser["computed"] = _computed(r, latest_batch=latest_batch, home=home, mode=mode)
        rows_out.append(ser)

    return jsonify({"ok": True, "rows": rows_out, "total": total,
                    "shown": shown, "badges": _badges()})


# ── GET /api/inbox/<id>/detail ────────────────────────────────────────────────
# ``signed=True``: demo/sample rows carry NEGATIVE ids (see demo_data), and the
# default int converter rejects a leading '-' (a 404 at the routing layer), which
# would dead-end the detail pane during onboarding. Signed matching lets a demo id
# reach the handler, where it's looked up in the demo snapshot.
@inbox_bp.get("/inbox/<int(signed=True):inbox_id>/detail")
def inbox_detail(inbox_id: int):
    """Server-computed detail for one row, mirroring the tk detail pane's pieces
    (all from data the pipeline already produced — no AI, no network):
    ``fit_why``, ``score_notes`` breakdown, ``ghost`` staleness verdict, ``ats``
    hint, ``description_preview``. 404 for an unknown id.

    Serves demo rows too (negative ids, not in the DB) so the detail pane works while
    the onboarding sample is on screen — they carry their own ``fit_why`` /
    ``score_notes`` / ``description`` inline, so the same pipeline-derived readout
    renders without any DB or network access."""
    rows = {r["id"]: r for r in _inbox_snapshot()}
    row = rows.get(inbox_id)
    if row is None:
        return jsonify({"ok": False, "error": "unknown inbox row"}), 404

    fit_why = (row.get("fit_why") or "").strip()
    score_notes = score_breakdown(row.get("score_notes") or "")

    ghost = {}
    try:
        ghost = ghostmod.ghost_score(row)
    except Exception:
        ghost = {}

    ats = {"ats": "", "matched": [], "missing": [], "have": 0, "lines": []}
    try:
        skill_terms = extract_skill_terms()
    except Exception:
        skill_terms = frozenset()
    try:
        hint = atshintmod.match_hint(row.get("description") or "",
                                     row.get("url", ""), skill_terms=skill_terms)
        ats = dict(hint)
        ats["lines"] = atshintmod.hint_lines(hint)
    except Exception:
        pass

    desc = " ".join((row.get("description") or "").split())[:500]

    return jsonify({"ok": True, "row": _ser_inbox_row(row),
                    "fit_why": fit_why, "score_notes": score_notes,
                    "ghost": ghost, "ats": ats, "description_preview": desc})


# ── single-row triage (Phase 1, kept) ─────────────────────────────────────────
@inbox_bp.post("/inbox/<int:inbox_id>/track")
@require_local_origin
def track(inbox_id: int):
    """Promote an inbox row to a tracked application. 404 if the row is gone."""
    app_id = service.track_job(inbox_id)
    if app_id is None:
        return jsonify({"ok": False, "error": "unknown inbox row"}), 404
    return jsonify({"ok": True, "app_id": app_id})


@inbox_bp.post("/inbox/<int:inbox_id>/dismiss")
@require_local_origin
def dismiss(inbox_id: int):
    """Dismiss an inbox row (hidden from future runs). 404 if the row is gone."""
    if not service.inbox_exists(inbox_id):
        return jsonify({"ok": False, "error": "unknown inbox row"}), 404
    service.dismiss_job(inbox_id)
    return jsonify({"ok": True})


# ── bulk triage + undo ────────────────────────────────────────────────────────
@inbox_bp.post("/inbox/dismiss-bulk")
@require_local_origin
def dismiss_bulk():
    """Dismiss many rows at once (mirrors the tk 'Dismiss all shown' / 'Dismiss
    company' bulk path). Body ``{ids:[int,...]}``. Stashes the dismissed row dicts
    server-side so undo-dismiss can re-insert them, and returns an ``undo_token``.
    Unknown ids are skipped (inclusion-over-precision: never error the whole batch
    over a stale id). Returns ``{ok, dismissed:n, undo_token?}``."""
    data = request.get_json(silent=True) or {}
    ids = data.get("ids") or []
    if not isinstance(ids, list):
        return jsonify({"ok": False, "error": "ids must be a list"}), 400
    # Snapshot the full row dicts BEFORE dismissing, so undo can restore them
    # (dismiss deletes the inbox row). Only rows that actually exist are dismissed.
    present = {r["id"]: r for r in db.inbox_all()}
    victims = []
    for raw in ids:
        try:
            rid = int(raw)
        except (TypeError, ValueError):
            continue
        row = present.get(rid)
        if row is not None:
            service.dismiss_job(rid)
            victims.append(row)
    token = _stash_undo(victims)
    body = {"ok": True, "dismissed": len(victims)}
    if token:
        body["undo_token"] = token
    return jsonify(body)


@inbox_bp.post("/inbox/undo-dismiss")
@require_local_origin
def undo_dismiss():
    """Restore a previously-dismissed batch (mirrors the tk Undo button). Body
    ``{undo_token?}`` — a token from a dismiss-bulk response, or omit it to undo the
    most recent batch. Uses ``service.restore_dismissed_rows`` (re-inserts + clears
    the dismissed markers). Returns ``{ok, restored:n}``; ``restored=0`` when there
    is nothing to undo."""
    data = request.get_json(silent=True) or {}
    token = data.get("undo_token")
    rows = _pop_undo(token)
    restored = service.restore_dismissed_rows(rows) if rows else 0
    return jsonify({"ok": True, "restored": restored})


@inbox_bp.post("/inbox/<int:inbox_id>/fit")
@require_local_origin
def set_fit(inbox_id: int):
    """Set a single row's Fit grade + rationale (parity with the tk single-row set;
    the tk InboxTab has no dedicated single-row-fit button, but the engine seam
    ``service.set_inbox_fit`` exists and the web detail pane offers a manual grade).
    Body ``{fit:int, why?:str}``. 404 for an unknown id, 400 for a non-int fit."""
    if not service.inbox_exists(inbox_id):
        return jsonify({"ok": False, "error": "unknown inbox row"}), 404
    data = request.get_json(silent=True) or {}
    try:
        fit = int(data.get("fit"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "fit must be an integer"}), 400
    why = str(data.get("why") or "")
    service.set_inbox_fit(inbox_id, fit, why)
    return jsonify({"ok": True})


@inbox_bp.post("/inbox/undo-rerank")
@require_local_origin
def undo_rerank():
    """Revert the most recent AI re-rank batch on ANY route (file import, clipboard
    paste, API auto-rank, MCP) via ``service.undo_last_rerank('any')`` — the same
    call the tk 'Undo AI ranking' button makes. Returns ``{ok, restored:n}``."""
    n = service.undo_last_rerank("any")
    return jsonify({"ok": True, "restored": n})


# ── AI round-trip: export / download / import / score-reply ────────────────────
def _export_dir() -> Path:
    """The locked-down base directory every export is written under and every
    download is served from: ``<workspace output>/rerank``. Resolved absolute so
    the download route can verify a requested file lives inside it (no traversal)."""
    base = Path(workspace.output_dir()) / "rerank"
    base.mkdir(parents=True, exist_ok=True)
    return base.resolve()


@inbox_bp.post("/inbox/export")
@require_local_origin
def export():
    """Write the AI round-trip export (csv[+md]+prompt) for the chosen scope to a
    timestamped folder under the export dir, and return download URLs. Body:
    ``{scope:'all'|'view', fmt?:'both'|'csv'|'md', compact?:bool, chunk_size?:int,
    filters?:{...}}``. ``scope='view'`` re-applies the same filters (passed in
    ``filters``) server-side so the export matches what the user sees. Demo rows are
    never exported. Returns ``{ok, files:[{name, download_url}], count}``."""
    from datetime import datetime

    data = request.get_json(silent=True) or {}
    scope = str(data.get("scope") or "all")
    fmt = str(data.get("fmt") or "both")
    if fmt not in ("both", "csv", "md"):
        fmt = "both"
    compact = bool(data.get("compact"))
    try:
        chunk_size = int(data["chunk_size"]) if data.get("chunk_size") else None
    except (TypeError, ValueError):
        chunk_size = None

    all_rows = list(db.inbox_all())
    if scope == "view":
        f = data.get("filters") or {}
        home = _resolve_home()
        mode = (f.get("location_mode") or "").strip() or None
        pay_floor = home["pay_floor"] if f.get("pay_floor") else None
        rows = inbox_filters.filter_rows(
            all_rows,
            min_score=f.get("min_score"),
            sources=f.get("sources") or [],
            size=(f.get("size") or None),
            unscored_only=bool(f.get("unscored_only")),
            new_only=bool(f.get("new_only")),
            hide_stale=bool(f.get("hide_stale")),
            pay_floor=pay_floor,
            location_mode=mode,
            home_area=home["home_area"], has_home=home["has_home"],
            remote_ok=home["remote_ok"], q=f.get("q"), all_rows=all_rows)
    else:
        rows = all_rows
    # Never hand the fictional sample inbox to the user's AI (defense in depth —
    # demo rows carry is_demo; the real inbox never does).
    rows = [r for r in rows if not r.get("is_demo")]
    if not rows:
        return jsonify({"ok": False, "error": "nothing to export"}), 400

    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    out_dir = (_export_dir() / stamp)
    try:
        paths = export_inbox(rows, out_dir, fmt=fmt,
                             chunk_size=chunk_size, compact=compact)
    except Exception as e:  # noqa: BLE001 — surface as a clean 500-ish error body
        return jsonify({"ok": False, "error": str(e)}), 500

    # Flatten the returned path dict into a de-duped file list with download urls.
    files: list[dict] = []
    seen: set[str] = set()
    ordered: list[Path] = []
    ordered.extend(paths.get("csvs") or ([paths["csv"]] if paths.get("csv") else []))
    if paths.get("md"):
        ordered.append(paths["md"])
    if paths.get("prompt"):
        ordered.append(paths["prompt"])
    for p in ordered:
        p = Path(p)
        rel = f"{stamp}/{p.name}"
        if rel in seen:
            continue
        seen.add(rel)
        files.append({"name": rel,
                      "download_url": f"/api/inbox/export/download/{rel}"})
    return jsonify({"ok": True, "files": files, "count": len(rows)})


@inbox_bp.get("/inbox/export/download/<path:name>")
def export_download(name: str):
    """Serve a previously-exported file. LOCKED to the export dir: the requested
    path is resolved and its real parent chain is verified to live inside the export
    base, so ``../`` traversal (or an absolute path) can't escape to another file —
    a mismatch is a 404, never a leak."""
    base = _export_dir()
    try:
        target = (base / name).resolve()
    except (OSError, ValueError):
        return jsonify({"ok": False, "error": "not found"}), 404
    # Containment check: target must be base itself's descendant. is_relative_to
    # (3.9+) is exact; the str-prefix fallback keeps parity on older paths.
    try:
        inside = target.is_relative_to(base)
    except AttributeError:  # pragma: no cover - Py<3.9
        inside = str(target).startswith(str(base) + __import__("os").sep)
    if not inside or not target.is_file():
        return jsonify({"ok": False, "error": "not found"}), 404
    return send_file(str(target), as_attachment=True, download_name=target.name)


@inbox_bp.post("/inbox/import")
@require_local_origin
def import_ai():
    """Apply an AI-returned re-rank file. Accepts EITHER a multipart upload
    (``file=<csv|json>``) OR a JSON body ``{text:'<pasted csv/json>'}``. ``policy``
    (form field or JSON key) in {overwrite,keep_existing,add_only}. A malformed
    file surfaces as ``result.errors`` (never a 500). Returns ``{ok, result:
    {matched, updated, unmatched:n, skipped, errors:[...]}}``."""
    import tempfile
    import os

    policy = "overwrite"
    tmp_path = None
    try:
        if request.files.get("file") is not None:
            up = request.files["file"]
            policy = (request.form.get("policy") or "overwrite").strip()
            suffix = ".json" if (up.filename or "").lower().endswith(".json") else ".csv"
            fd, tmp_path = tempfile.mkstemp(suffix=suffix)
            os.close(fd)
            up.save(tmp_path)
            src = tmp_path
        else:
            data = request.get_json(silent=True) or {}
            text = data.get("text")
            if not text or not str(text).strip():
                return jsonify({"ok": False,
                                "error": "no file or text provided"}), 400
            policy = (data.get("policy") or "overwrite").strip()
            suffix = ".json" if str(text).lstrip()[:1] in ("[", "{") else ".csv"
            fd, tmp_path = tempfile.mkstemp(suffix=suffix)
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(str(text))
            src = tmp_path

        if policy not in ("overwrite", "keep_existing", "add_only"):
            return jsonify({"ok": False,
                            "error": f"unknown policy {policy!r}"}), 400

        rows_by_key = service.inbox_rows_by_key()
        res = import_scores(src, rows_by_key, policy=policy)
        return jsonify({"ok": True, "result": {
            "matched": res.matched,
            "updated": res.updated,
            "unmatched": len(res.unmatched),
            "skipped": res.skipped,
            "errors": list(res.errors),
        }})
    finally:
        if tmp_path:
            try:
                os.remove(tmp_path)
            except OSError:
                pass


@inbox_bp.post("/inbox/score-reply")
@require_local_origin
def score_reply():
    """Clipboard-bridge paste path: take a pasted AI fit reply and write its scores
    back onto the currently-unscored inbox rows (the same batch the tk 'Ask AI to
    rank' + 'Paste AI ranking' flow builds). Body ``{text:'<reply>'}``. Builds the
    compact prompt's job set from unscored rows, applies token-verified scores under
    one undoable batch, and reports counts. Returns ``{ok, applied, asked,
    missed:n}``; a parse failure is a clean 400."""
    from claude_bridge import BridgeParseError

    data = request.get_json(silent=True) or {}
    text = data.get("text")
    if not text or not str(text).strip():
        return jsonify({"ok": False, "error": "no reply text provided"}), 400

    # Build the same job set the export/prompt path uses: a diverse batch of
    # still-unscored rows (round-robin order from inbox_all), so pasted scores land
    # on the rows the user would have asked the AI to rank.
    rows = service.unscored_inbox_rows(list(db.inbox_all()), per_company=2, limit=20)
    _prompt, jobs, _dropped = service.compact_fit_prompt_for_rows(rows)
    if not jobs:
        return jsonify({"ok": True, "applied": 0, "asked": 0, "missed": 0})
    try:
        applied, missed = service.score_inbox_from_reply(jobs, str(text), source="bridge")
    except BridgeParseError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    return jsonify({"ok": True, "applied": applied,
                    "asked": len(jobs), "missed": len(missed)})
