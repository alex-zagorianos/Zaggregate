"""Applications (tracker) API — Phase 2.

Full CRUD surface over the tracked-applications table, re-hosting the engine seam
``tracker.service`` / ``tracker.db`` verbatim (no hand-rolled SQL), so the web
Tracker + Kanban are just another view of the same source of truth the tk GUI
uses. Every mutating route is origin-gated (``require_local_origin``) and returns
the ``{ok:true,...}`` / ``{ok:false,error}`` envelope.

Routes (mounted under ``/api`` by the api blueprint assembler):

* ``GET    /api/applications``                     list + counts + followups badge
* ``POST   /api/applications``                     add a manual application  [gate]
* ``GET    /api/applications/<id>``                one call powering JobDialog
* ``PATCH  /api/applications/<id>``                edit fields               [gate]
* ``POST   /api/applications/<id>/status``         funnel move               [gate]
* ``POST   /api/applications/<id>/archive``        soft-hide                 [gate]
* ``POST   /api/applications/<id>/restore``        un-hide                   [gate]
* ``DELETE /api/applications/<id>``                permanent delete          [gate]
* ``POST   /api/applications/<id>/notes``          timestamped note          [gate]
* ``POST   /api/applications/<id>/rounds``         add interview round       [gate]
* ``PATCH  /api/applications/<id>/rounds/<rid>``   edit round                [gate]
* ``DELETE /api/applications/<id>/rounds/<rid>``   delete round              [gate]
* ``GET    /api/applications/<id>/rounds/<rid>/ics`` download the .ics event

The ``.ics`` download writes the VEVENT to a private temp dir via
``tracker.service.write_round_ics`` and streams it as an attachment — NEVER shells
out to explorer (repo rule: all file handoffs are HTTP downloads).
"""
from __future__ import annotations

import tempfile

from flask import Blueprint, request, jsonify, send_file

from tracker import db
from tracker import service
from ..security import require_local_origin
from ..serializers import app_row, app_row_list

applications_bp = Blueprint("webui_applications", __name__)


# ── helpers ───────────────────────────────────────────────────────────────────

def _body() -> dict:
    """Parse a JSON body defensively, always returning a dict. A non-object body
    (list, scalar, junk) collapses to ``{}`` so callers can validate individual
    fields rather than crashing on ``.get``."""
    data = request.get_json(force=True, silent=True)
    return data if isinstance(data, dict) else {}


def _timeline(app_id: int) -> list[dict]:
    """The status/notes timeline for an application (already JSON-safe dicts)."""
    return service.status_timeline(app_id)


# ── list + counts ─────────────────────────────────────────────────────────────

@applications_bp.get("/applications")
def list_applications():
    """Active applications (mirroring the tk TrackerTab default) plus the funnel
    counts and the follow-ups-due badge, so one call powers the whole tab header.

    ``status`` query param: a specific status filters within non-archived;
    ``archived`` returns only archived rows; ``all`` (the default) returns every
    non-archived application, newest first."""
    status = request.args.get("status")
    if status in (None, "", "all"):
        rows = service.list_jobs()               # non-archived, all statuses
    else:
        rows = service.list_jobs(status)         # "archived" special-cased in db
    return jsonify({
        "ok": True,
        "rows": [app_row_list(r) for r in rows],
        "counts": db.get_counts(),
        "followups_due": db.count_followups_due(),
    })


@applications_bp.post("/applications")
@require_local_origin
def add_application():
    """Add a manually-entered application. ``title`` and ``company`` are required
    (mirrors ``tracker/app.py``'s ``/api/add`` validation); everything else is
    optional. Returns the new row id."""
    data = _body()
    title = (data.get("title") or "").strip()
    company = (data.get("company") or "").strip()
    if not title or not company:
        return jsonify({"ok": False, "error": "title and company are required"}), 400
    app_id = service.add_manual_job(
        title=title,
        company=company,
        location=(data.get("location") or "").strip(),
        url=(data.get("url") or "").strip(),
        salary_text=(data.get("salary_text") or "").strip(),
        source=data.get("source") or "manual",
        status=data.get("status") or "interested",
        date_applied=(data.get("date_applied") or "").strip(),
        notes=(data.get("notes") or "").strip(),
    )
    return jsonify({"ok": True, "id": app_id}), 201


# ── single application (powers JobDialog) ─────────────────────────────────────

@applications_bp.get("/applications/<int:app_id>")
def get_application(app_id: int):
    """Everything the JobDialog needs in one call: the application row, its
    status/notes timeline, its interview rounds, a referral hint for the company,
    and the status vocabulary (values + labels) so the client renders the status
    picker without a second request."""
    job = service.get_job(app_id)
    if job is None:
        return jsonify({"ok": False, "error": "unknown application"}), 404
    return jsonify({
        "ok": True,
        "job": app_row(job),
        "timeline": _timeline(app_id),
        "rounds": service.list_interview_rounds(app_id),
        "referral": service.referral_hint(job.get("company", "") or ""),
        "network": _network_block(job.get("company", "") or ""),
        "statuses": db.STATUSES,
        "status_labels": db.STATUS_LABELS,
    })


# ── referral network (B4) ─────────────────────────────────────────────────────
def _network_block(company: str) -> dict:
    """``{count, contacts:[{name, position}]}`` for the imported-network people the
    user knows at ``company`` (top 5). Distinct from the tracker's manual-``contacts``
    referral hint above (that's the hand-entered CRM; this is the bulk LinkedIn/
    Google import). Best-effort — never breaks the detail response."""
    try:
        import network as networkmod
        people = networkmod.matches_for(company)
    except Exception:
        return {"count": 0, "contacts": []}
    return {
        "count": len(people),
        "contacts": [{"name": p.get("name", ""), "position": p.get("position", "")}
                     for p in people[:5]],
    }


@applications_bp.get("/applications/<int:app_id>/warm-path-prompt")
def warm_path_prompt(app_id: int):
    """The BYO-AI warm-path prompt for a tracked application (prompt-only, no
    paste-back). 404 for an unknown id. Reuses the inbox blueprint's builder so the
    inbox + application prompts are byte-identical for the same job context."""
    job = service.get_job(app_id)
    if job is None:
        return jsonify({"ok": False, "error": "unknown application"}), 404
    from .inbox import _build_warm_path
    return jsonify({"ok": True, "prompt": _build_warm_path(job)})


# ── outreach: follow-up / thank-you + interview prep (B5) ─────────────────────

def _experience_text() -> str:
    """The raw experience.md for the active project, best-effort. Empty string when
    the file is missing/unreadable — the prompt builders degrade gracefully."""
    import workspace
    from pathlib import Path
    try:
        return Path(workspace.experience_file()).read_text(encoding="utf-8")
    except OSError:
        return ""


@applications_bp.get("/applications/<int:app_id>/followup-prompt")
def followup_prompt(app_id: int):
    """The BYO-AI follow-up / thank-you prompt for a tracked application
    (prompt-only, no paste-back). Auto-selects a post-interview THANK-YOU vs a
    post-apply FOLLOW-UP from the application's status + interview rounds. 404 for
    an unknown id. Returns ``{ok, prompt, stage}`` so the client can label the
    surface consistently with the note that was actually drafted."""
    job = service.get_job(app_id)
    if job is None:
        return jsonify({"ok": False, "error": "unknown application"}), 404
    import outreach
    job["_rounds"] = service.list_interview_rounds(app_id)
    stage = outreach.followup_stage(job)
    return jsonify({"ok": True, "stage": stage,
                    "prompt": outreach.build_followup_prompt(job, stage)})


@applications_bp.get("/applications/<int:app_id>/interview-prep-prompt")
def interview_prep_prompt(app_id: int):
    """The BYO-AI interview-prep prompt for a tracked application (prompt-only, no
    paste-back). Grounds the practice answers in the user's experience.md. 404 for
    an unknown id."""
    job = service.get_job(app_id)
    if job is None:
        return jsonify({"ok": False, "error": "unknown application"}), 404
    import outreach
    return jsonify({"ok": True,
                    "prompt": outreach.build_interview_prep_prompt(
                        job, _experience_text())})


@applications_bp.patch("/applications/<int:app_id>")
@require_local_origin
def update_application(app_id: int):
    """Edit one or more application fields. An unknown field name is a 400 that
    NAMES the offending field(s) (via ``UnknownFieldError``) rather than silently
    dropping the value (S32/L3); an unknown id is a 404. An empty body is a no-op
    that returns the (unchanged) refetched row."""
    if service.get_job(app_id) is None:
        return jsonify({"ok": False, "error": "unknown application"}), 404
    data = _body()
    try:
        service.update_job(app_id, **data)
    except db.UnknownFieldError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    return jsonify({"ok": True, "job": app_row(service.get_job(app_id))})


@applications_bp.post("/applications/<int:app_id>/status")
@require_local_origin
def set_application_status(app_id: int):
    """Set an application's status. The kanban drag-drop target AND the general
    status-edit seam. Validates the requested status against ``db.STATUSES`` (a bad
    status is a 400) and 404s an unknown id, then writes it through
    ``service.set_status`` (which records the status_history transition +
    auto-stamps date_applied on 'applied'). Returns the refetched row so the client
    reflects any auto-stamped side effects.

    Forward-only is a UI CONVENTION, not an engine invariant, and this endpoint
    intentionally accepts ANY valid status — including a backward move. The Board's
    "only advances forward" guarantee (``board-logic.ts`` ``canDrop`` /
    ``rejectReason``) is enforced entirely client-side off the server-supplied
    ``forward_targets`` list (``ui.kanban_core.forward_targets``); the server is
    deliberately the permissive escape hatch that the tk job-editor's freeform
    status field and the JobDialog's status picker both rely on to correct a status
    to an arbitrary value. Do NOT add a ``forward_targets`` gate here — it would
    break those legitimate corrections. (``kanban_core.forward_targets`` documents
    the same split: the db model permits any status set; the board merely surfaces
    non-downgrading choices.)"""
    if service.get_job(app_id) is None:
        return jsonify({"ok": False, "error": "unknown application"}), 404
    status = (_body().get("status") or "").strip()
    if status not in db.STATUSES:
        return jsonify({"ok": False, "error": f"invalid status {status!r}"}), 400
    service.set_status(app_id, status)
    return jsonify({"ok": True, "job": app_row(service.get_job(app_id))})


@applications_bp.post("/applications/<int:app_id>/archive")
@require_local_origin
def archive_application(app_id: int):
    """Soft-delete (hide from normal views/counts; keep the row + its dedup URL)."""
    if service.get_job(app_id) is None:
        return jsonify({"ok": False, "error": "unknown application"}), 404
    service.archive_job(app_id)
    return jsonify({"ok": True})


@applications_bp.post("/applications/<int:app_id>/restore")
@require_local_origin
def restore_application(app_id: int):
    """Un-archive a previously soft-deleted application."""
    if service.get_job(app_id) is None:
        return jsonify({"ok": False, "error": "unknown application"}), 404
    service.restore_job(app_id)
    return jsonify({"ok": True})


@applications_bp.delete("/applications/<int:app_id>")
@require_local_origin
def delete_application(app_id: int):
    """Permanent delete (reachable only from the archive view in the UI)."""
    if service.get_job(app_id) is None:
        return jsonify({"ok": False, "error": "unknown application"}), 404
    service.delete_job(app_id)
    return jsonify({"ok": True})


# ── per-stage notes ───────────────────────────────────────────────────────────

@applications_bp.post("/applications/<int:app_id>/notes")
@require_local_origin
def add_note(app_id: int):
    """Attach a timestamped note WITHOUT changing status. A blank note is a 400
    (nothing to record); an unknown id is a 404. Returns the refreshed timeline so
    the JobDialog's timeline pane updates in one round-trip."""
    if service.get_job(app_id) is None:
        return jsonify({"ok": False, "error": "unknown application"}), 404
    note = (_body().get("note") or "").strip()
    if not note:
        return jsonify({"ok": False, "error": "note is required"}), 400
    service.add_status_note(app_id, note)
    return jsonify({"ok": True, "timeline": _timeline(app_id)})


# ── interview rounds (sub-CRUD) ───────────────────────────────────────────────

_ROUND_FIELDS = ("kind", "scheduled_at", "interviewer", "notes", "outcome",
                 "round_no")


@applications_bp.post("/applications/<int:app_id>/rounds")
@require_local_origin
def add_round(app_id: int):
    """Add an interview round to an application. Adding a round on a pre-interview
    status advances the funnel (engine coherence, S32/L4). Returns the new round id
    plus the refreshed rounds list."""
    if service.get_job(app_id) is None:
        return jsonify({"ok": False, "error": "unknown application"}), 404
    data = _body()
    fields = {k: data[k] for k in _ROUND_FIELDS if k in data}
    rid = service.add_interview_round(app_id, **fields)
    return jsonify({
        "ok": True,
        "id": rid,
        "rounds": service.list_interview_rounds(app_id),
    }), 201


@applications_bp.patch("/applications/<int:app_id>/rounds/<int:rid>")
@require_local_origin
def update_round(app_id: int, rid: int):
    """Edit an interview round. An unknown round field is a 400 that names it
    (``UnknownFieldError``); an unknown round id (or one belonging to another app)
    is a 404. Returns the refreshed rounds list."""
    rnd = service.get_interview_round(rid)
    if rnd is None or int(rnd.get("app_id", -1)) != app_id:
        return jsonify({"ok": False, "error": "unknown interview round"}), 404
    data = _body()
    try:
        service.update_interview_round(rid, **data)
    except db.UnknownFieldError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    return jsonify({"ok": True, "rounds": service.list_interview_rounds(app_id)})


@applications_bp.delete("/applications/<int:app_id>/rounds/<int:rid>")
@require_local_origin
def delete_round(app_id: int, rid: int):
    """Delete an interview round. 404 for an unknown round or one under another
    application. Returns the refreshed rounds list."""
    rnd = service.get_interview_round(rid)
    if rnd is None or int(rnd.get("app_id", -1)) != app_id:
        return jsonify({"ok": False, "error": "unknown interview round"}), 404
    service.delete_interview_round(rid)
    return jsonify({"ok": True, "rounds": service.list_interview_rounds(app_id)})


@applications_bp.get("/applications/<int:app_id>/rounds/<int:rid>/ics")
def round_ics(app_id: int, rid: int):
    """Download a round as an ``.ics`` calendar event. Writes the VEVENT to a
    private temp dir via ``service.write_round_ics`` and streams it back as an
    attachment (all file handoffs are HTTP downloads — never a shelled-out
    explorer). A round with no ``scheduled_at`` is a 400 (nothing to schedule);
    an unknown app/round is a 404. This is a READ (no side effect the user cares
    about), so it is not origin-gated."""
    job = service.get_job(app_id)
    if job is None:
        return jsonify({"ok": False, "error": "unknown application"}), 404
    rnd = service.get_interview_round(rid)
    if rnd is None or int(rnd.get("app_id", -1)) != app_id:
        return jsonify({"ok": False, "error": "unknown interview round"}), 404
    tmp = tempfile.mkdtemp(prefix="zag-ics-")
    try:
        path = service.write_round_ics(job, rnd, tmp)
    except ValueError as e:
        # No scheduled_at — the round can't become a calendar event yet.
        return jsonify({"ok": False, "error": str(e)}), 400
    return send_file(
        str(path),
        mimetype="text/calendar",
        as_attachment=True,
        download_name=path.name,
    )
