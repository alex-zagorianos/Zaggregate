"""Apply Queue API — resume/batch/rank throughput surface (Phase 4).

Re-hosts the tk ``ApplyQueueTab`` over HTTP without importing Tk. Every 'interested'
application, ranked best-first, with the same per-job actions: copy a resume prompt,
paste a claude.ai reply -> DOCX bundle, a batch-of-5 round-trip, a server-side API
generate (only when a key is configured), and the AI fit-ranking prompt/reply pair.

Parity anchors (byte-for-byte with ``ApplyQueueTab``):
* ordering = ``fit_score`` desc then ``score`` desc (``(fit or -1, score or -1)``,
  reverse) — mirrors ``ApplyQueueTab.refresh``;
* the resume prompt header is ``Title/Company/Location`` + the saved description,
  identical to ``_copy_resume_prompt`` / ``_copy_batch_prompt``;
* batch default = the next ``_BATCH_LIMIT`` (5) queue jobs that still need docs AND
  have a saved description (batch mode can't stop to ask for a paste);
* fit ranking routes through ``tracker.service.compact_fit_prompt_for_rows`` /
  ``score_applications_from_reply`` (preference-anchored, token-verified) exactly as
  the tk tab does.

Generate + rank single-flight per project via the shared ``JobRunner`` exclusive
mutex is NOT reused here (those are engine-INGEST jobs); instead a lightweight
per-project ``threading.Lock`` guards the API-calling routes (generate/rank-reply),
matching the tk tab's ``_api_ranking`` / ``_set_busy`` single-flight guard. The
Anthropic key never leaves the server (``ui.common._call_prompt_via_api`` /
``resume.service.save_bundle`` call it server-side).

Downloads go through the shared traversal-locked ``webui.downloads`` family, locked
to ``workspace.output_dir()`` (the resume-bundle write target).
"""
from __future__ import annotations

import threading

from flask import Blueprint, jsonify, request

import workspace
from claude_bridge import BridgeParseError
from match import ats_hint as atshintmod
from tracker import service
from tracker.db import get_all
from ..security import require_local_origin
from ..serializers import app_row as _ser_app
from .. import downloads

queue_bp = Blueprint("webui_queue", __name__)

_BATCH_LIMIT = 5  # resumes per paste round-trip (mirrors ApplyQueueTab._BATCH_LIMIT)

# Per-project single-flight for the API-calling routes (generate / rank-reply):
# overlapping API calls waste tokens and (for rank) break one-click Undo, exactly
# the reason the tk tab guards with `_api_ranking` / a disabled action bar. A
# process-local dict of locks keyed by project slug; a non-blocking acquire returns
# 409 so a second in-flight request fails fast rather than queueing.
_project_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def _project_lock(slug: str) -> threading.Lock:
    with _locks_guard:
        lock = _project_locks.get(slug)
        if lock is None:
            lock = threading.Lock()
            _project_locks[slug] = lock
        return lock


def _download_base():
    """The traversal-lock base for queue resume downloads = the active project's
    output dir (where ``save_bundle_from_data`` writes)."""
    return downloads.output_subtree()


def _download_url(path) -> str:
    """A gated download URL for a saved bundle file, relative to the output-dir
    base. ``path`` may be absolute (as save_bundle returns) — we key the download by
    basename, which the locked route resolves back under the base."""
    from pathlib import Path
    return f"/api/queue/download/{Path(path).name}"


def _ranked_interested() -> list[dict]:
    """Every 'interested' application, ranked fit-else-score desc — the EXACT
    ordering ``ApplyQueueTab.refresh`` uses (``(fit_score or -1, score or -1)``,
    reverse)."""
    jobs = get_all("interested")
    jobs.sort(key=lambda j: (j.get("fit_score") or -1, j.get("score") or -1),
              reverse=True)
    return jobs


# ── list ──────────────────────────────────────────────────────────────────────
@queue_bp.get("/queue")
def queue_list():
    """The ranked apply queue: ``{ok, rows:[app_row + {ats_label, referral,
    docs_path?}]}`` ordered fit-else-score desc. ``ats_label`` (URL-only, no
    network) and ``referral`` (known contacts at the company) mirror the tk detail
    pane's per-row hints; ``docs_path`` is the saved resume path when present."""
    rows = []
    for j in _ranked_interested():
        row = _ser_app(j)
        try:
            row["ats_label"] = atshintmod.ats_label(j.get("url", "")) or ""
        except Exception:  # noqa: BLE001 — hint only
            row["ats_label"] = ""
        try:
            row["referral"] = service.referral_hint(j.get("company", "")) or ""
        except Exception:  # noqa: BLE001
            row["referral"] = ""
        if j.get("resume_path"):
            row["docs_path"] = j["resume_path"]
        rows.append(row)
    return jsonify({"ok": True, "rows": rows})


# ── single-job resume prompt / paste ──────────────────────────────────────────
def _posting_block(job: dict) -> str:
    """The Title/Company/Location + description block the tk tab feeds build_prompt.
    Byte-for-byte ``ApplyQueueTab._copy_resume_prompt``'s f-string."""
    return (f"Title: {job['title']}\nCompany: {job['company']}\n"
            f"Location: {job.get('location','')}\n\n{job.get('description','') or ''}")


@queue_bp.get("/queue/<int:job_id>/resume-prompt")
def resume_prompt(job_id: int):
    """The clipboard resume-tailoring prompt for one queue job. ``{ok, prompt}``.
    404 for an unknown job; 400 when the job has no saved description (the tk tab
    would pop a paste dialog — over HTTP the client must supply the posting via the
    Resume tab instead, so we surface a clear 400)."""
    job = service.get_job(job_id)
    if not job:
        return jsonify({"ok": False, "error": "unknown job"}), 404
    if not (job.get("description") or "").strip():
        return jsonify({"ok": False,
                        "error": "no saved description for this job — use the "
                                 "Resume tab to paste the posting"}), 400
    from resume.service import build_prompt
    try:
        prompt = build_prompt(_posting_block(job))
    except Exception as e:  # noqa: BLE001
        return jsonify({"ok": False, "error": str(e)}), 400
    return jsonify({"ok": True, "prompt": prompt})


@queue_bp.post("/queue/<int:job_id>/resume-from-paste")
@require_local_origin
def resume_from_paste(job_id: int):
    """Parse a pasted claude.ai reply -> resume/cover DOCX bundle for one job,
    saving the resume path onto the application (mirrors the tk Paste Reply flow).
    Body ``{text}``. ``{ok, files:[{name, download_url}]}``. A ``BridgeParseError``
    is a clean 400 carrying its message; unknown job -> 404."""
    job = service.get_job(job_id)
    if not job:
        return jsonify({"ok": False, "error": "unknown job"}), 404
    data = request.get_json(silent=True) or {}
    text = str(data.get("text") or "")
    if not text.strip():
        return jsonify({"ok": False, "error": "no reply text"}), 400
    from claude_bridge import parse_resume_response
    from resume.service import save_bundle_from_data
    try:
        parsed = parse_resume_response(text)
        resume_path, cover_path = save_bundle_from_data(
            parsed, workspace.output_dir(), company=job["company"])
    except BridgeParseError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except Exception as e:  # noqa: BLE001 — DOCX render failure
        return jsonify({"ok": False, "error": str(e)}), 500
    service.update_job(job_id, resume_path=str(resume_path),
                       cover_path=str(cover_path) if cover_path else "")
    return jsonify({"ok": True, "files": _files_payload(resume_path, cover_path)})


# ── batch prompt / paste ──────────────────────────────────────────────────────
@queue_bp.post("/queue/batch-prompt")
@require_local_origin
def batch_prompt():
    """One prompt covering the next few queue jobs that still need docs (mirrors the
    tk Batch Prompt button). Body ``{ids?:[int]}`` — when given, those jobs are the
    pool (in queue order); otherwise the whole queue. Only jobs WITHOUT a saved
    resume AND WITH a saved description qualify (batch mode can't ask for a paste),
    capped at ``_BATCH_LIMIT`` (5). Returns ``{ok, prompt, ids}`` where ``ids`` is
    the batch order (1-based reply slots map to these). 400 when nothing qualifies."""
    data = request.get_json(silent=True) or {}
    ranked = _ranked_interested()
    id_filter = data.get("ids")
    if isinstance(id_filter, list) and id_filter:
        wanted = {int(i) for i in id_filter if _intish(i)}
        pool = [j for j in ranked if j["id"] in wanted]
    else:
        pool = ranked
    batch = [j for j in pool
             if not j.get("resume_path")
             and (j.get("description") or "").strip()][:_BATCH_LIMIT]
    if not batch:
        return jsonify({"ok": False,
                        "error": "no queued jobs with a saved description still "
                                 "need docs"}), 400
    from resume.service import build_batch_prompt
    postings = [_posting_block(j) for j in batch]
    try:
        prompt = build_batch_prompt(postings)
    except Exception as e:  # noqa: BLE001
        return jsonify({"ok": False, "error": str(e)}), 400
    return jsonify({"ok": True, "prompt": prompt, "ids": [j["id"] for j in batch]})


@queue_bp.post("/queue/batch-from-paste")
@require_local_origin
def batch_from_paste():
    """Parse a pasted batch reply -> per-job DOCX bundles (mirrors the tk Paste
    Batch flow). Body ``{text, ids:[int]}`` — ``ids`` is the batch order returned by
    /queue/batch-prompt; reply slot N (1-based) maps to ``ids[N-1]``. Returns
    ``{ok, results:[{id, files}|{id, error}]}`` — one entry per matched, saved job;
    a per-job DOCX failure is reported inline, not as a whole-request error. A
    ``BridgeParseError`` on the reply itself is a clean 400. Slots outside the ids
    range are ignored (parity with the tk ``1 <= n <= len`` guard)."""
    data = request.get_json(silent=True) or {}
    text = str(data.get("text") or "")
    ids = data.get("ids")
    if not text.strip():
        return jsonify({"ok": False, "error": "no reply text"}), 400
    if not isinstance(ids, list) or not ids:
        return jsonify({"ok": False, "error": "missing ids"}), 400
    order = [int(i) for i in ids if _intish(i)]
    from claude_bridge import parse_batch_resume_response
    from resume.service import save_bundle_from_data
    try:
        parsed = parse_batch_resume_response(text)
    except BridgeParseError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    results = []
    for n, bundle_data in parsed.items():
        if not (1 <= n <= len(order)):
            continue
        job = service.get_job(order[n - 1])
        if not job:
            continue
        try:
            resume_path, cover_path = save_bundle_from_data(
                bundle_data, workspace.output_dir(), company=job["company"])
        except Exception as e:  # noqa: BLE001 — per-job failure, keep the batch going
            results.append({"id": job["id"], "error": str(e)})
            continue
        service.update_job(job["id"], resume_path=str(resume_path),
                           cover_path=str(cover_path) if cover_path else "")
        results.append({"id": job["id"],
                        "files": _files_payload(resume_path, cover_path)})
    return jsonify({"ok": True, "results": results})


# ── server-side API generate (single-flight) ──────────────────────────────────
@queue_bp.post("/queue/<int:job_id>/generate")
@require_local_origin
def generate(job_id: int):
    """Server-side resume generation via the Anthropic API for one job (mirrors the
    tk 'Generate via API' button). 409 ``{error:'no api key'}`` when no key is
    configured (``resume.service.api_available()``). 404 for an unknown job; 400
    when the job has no saved description. Single-flight per project (a 409
    ``{error:'busy'}`` if a generate/rank is already running for this project). The
    key never leaves the server. ``{ok, files:[...]}`` on success."""
    from resume.service import api_available
    if not api_available():
        return jsonify({"ok": False, "error": "no api key"}), 409
    job = service.get_job(job_id)
    if not job:
        return jsonify({"ok": False, "error": "unknown job"}), 404
    posting = (job.get("description") or "").strip()
    if not posting:
        return jsonify({"ok": False,
                        "error": "no saved description for this job"}), 400

    slug = str(workspace.active_slug() or "")
    lock = _project_lock(slug)
    if not lock.acquire(blocking=False):
        return jsonify({"ok": False, "error": "busy"}), 409
    try:
        from resume.service import save_bundle
        resume_path, cover_path = save_bundle(
            _posting_block(job), workspace.output_dir(), company=job["company"])
    except Exception as e:  # noqa: BLE001 — API/DOCX failure
        return jsonify({"ok": False, "error": str(e)}), 500
    finally:
        lock.release()
    service.update_job(job_id, resume_path=str(resume_path),
                       cover_path=str(cover_path) if cover_path else "")
    return jsonify({"ok": True, "files": _files_payload(resume_path, cover_path)})


# ── AI fit ranking (prompt / reply) ───────────────────────────────────────────
@queue_bp.post("/queue/rank")
@require_local_origin
def rank():
    """AI fit-ranking for the queue (mirrors the tk 'Ask AI to rank' / 'Paste AI
    ranking' pair). Body ``{mode:'prompt'}`` -> ``{ok, prompt, ids, dropped}``
    built from the top queue rows via ``compact_fit_prompt_for_rows`` (top-20, same
    as the tk ``list(self._rows.values())[:20]``); ``{mode:'reply', text}`` ->
    applies the reply's scores via ``score_applications_from_reply`` under one
    undoable batch and returns ``{ok, applied}``. The reply path is single-flight
    per project (409 ``busy``). A parse failure on the reply is a clean 400.
    ``mode='prompt'`` with everything auto-filtered returns 200 ``{ok, prompt:'',
    ids:[], dropped}`` so the client can explain why."""
    data = request.get_json(silent=True) or {}
    mode = str(data.get("mode") or "prompt")

    if mode == "prompt":
        rows = _ranked_interested()[:20]
        if not rows:
            return jsonify({"ok": True, "prompt": "", "ids": [], "dropped": []})
        # kept jobs are JobResults carrying the row id in .job_id; dropped are dicts
        # {id, title, company, reasons} (compact_fit_prompt_for_rows contract).
        prompt, jobs, dropped = service.compact_fit_prompt_for_rows(rows)
        drop_out = [{"id": d.get("id"), "title": d.get("title"),
                     "company": d.get("company"), "reasons": d.get("reasons", [])}
                    for d in (dropped or [])]
        if not jobs:
            return jsonify({"ok": True, "prompt": "", "ids": [],
                            "dropped": drop_out})
        return jsonify({"ok": True, "prompt": prompt,
                        "ids": [_job_id_of(j) for j in jobs],
                        "dropped": drop_out})

    if mode == "reply":
        text = str(data.get("text") or "")
        if not text.strip():
            return jsonify({"ok": False, "error": "no reply text"}), 400
        # Rebuild the SAME job set the prompt was built from (top-20 -> compact
        # filter), so token-verified scoring lands on the right applications —
        # exactly what the tk _paste_fit path holds in self._fit_jobs.
        rows = _ranked_interested()[:20]
        _prompt, jobs, _dropped = service.compact_fit_prompt_for_rows(rows)
        if not jobs:
            return jsonify({"ok": True, "applied": 0})
        slug = str(workspace.active_slug() or "")
        lock = _project_lock(slug)
        if not lock.acquire(blocking=False):
            return jsonify({"ok": False, "error": "busy"}), 409
        try:
            applied = service.score_applications_from_reply(jobs, text)
        except BridgeParseError as e:
            return jsonify({"ok": False, "error": str(e)}), 400
        finally:
            lock.release()
        return jsonify({"ok": True, "applied": applied})

    return jsonify({"ok": False, "error": f"unknown mode {mode!r}"}), 400


# ── downloads ─────────────────────────────────────────────────────────────────
@queue_bp.get("/queue/download/<path:name>")
def queue_download(name: str):
    """Serve a generated resume/cover DOCX, LOCKED to the active project's output
    dir (traversal -> 404 via the shared downloads gate). Attachment download; never
    shells to explorer."""
    return downloads.send_locked(_download_base(), name)


# ── helpers ───────────────────────────────────────────────────────────────────
def _files_payload(resume_path, cover_path) -> list[dict]:
    """The ``[{name, download_url}]`` list for a saved bundle (resume + optional
    cover), each keyed by basename through the locked download route."""
    from pathlib import Path
    files = [{"name": Path(resume_path).name,
              "download_url": _download_url(resume_path)}]
    if cover_path:
        files.append({"name": Path(cover_path).name,
                      "download_url": _download_url(cover_path)})
    return files


def _intish(value) -> bool:
    try:
        int(value)
        return True
    except (TypeError, ValueError):
        return False


def _job_id_of(job) -> int | None:
    """The application id a kept fit-job carries (JobResult.job_id, a string). None
    when absent/non-numeric."""
    jid = getattr(job, "job_id", None)
    try:
        return int(jid) if jid else None
    except (TypeError, ValueError):
        return None
