"""Resume Generator API — standalone paste-a-posting -> DOCX (Phase 4).

Re-hosts the tk ``ResumeTab`` over HTTP without importing Tk: paste a job posting,
get a tailoring prompt (``build_prompt``), paste the claude.ai reply back, get the
resume + cover-letter DOCX as gated downloads (replacing the tk 'reveal in
explorer' — repo rule: all file handoffs are HTTP downloads, server code never
shells to explorer).

Parity with ``ResumeTab``:
* the prompt is ``resume.service.build_prompt(posting)`` — identical to the tk
  '1. Copy Prompt' path;
* the paste path is ``data_from_paste`` -> ``save_bundle_from_data(data,
  workspace.output_dir())`` — identical to '2. Paste Reply ▸ DOCX', a
  ``BridgeParseError`` surfaced as a clean 400.

Downloads share ``webui.downloads`` locked to ``workspace.output_dir()`` (the same
base the queue resume downloads use — one output subtree, one lock).
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

import workspace
from claude_bridge import BridgeParseError
from ..security import require_local_origin
from .. import downloads

resume_bp = Blueprint("webui_resume", __name__)


def _download_base():
    """Traversal-lock base for resume downloads = the active project's output dir."""
    return downloads.output_subtree()


@resume_bp.post("/resume/prompt")
def resume_prompt():
    """Build a resume-tailoring prompt for a pasted posting (the tk '1. Copy
    Prompt'). READ-only (no side effect, no gate needed — matches the tk prompt
    build). Body ``{posting_text}``. ``{ok, prompt}``. 400 for an empty posting."""
    data = request.get_json(silent=True) or {}
    posting = str(data.get("posting_text") or "").strip()
    if not posting:
        return jsonify({"ok": False, "error": "paste a job posting first"}), 400
    from resume.service import build_prompt
    try:
        prompt = build_prompt(posting)
    except Exception as e:  # noqa: BLE001 — surface build/validation errors as 400
        return jsonify({"ok": False, "error": str(e)}), 400
    return jsonify({"ok": True, "prompt": prompt})


@resume_bp.post("/resume/from-paste")
@require_local_origin
def resume_from_paste():
    """Parse a pasted claude.ai reply into resume/cover DOCX and return gated
    download URLs (the tk '2. Paste Reply ▸ DOCX'). Body ``{reply_text,
    posting_text?}`` — ``posting_text`` is accepted for symmetry/future company
    tagging but the tk paste path doesn't use it, so it's optional and ignored for
    the bundle contents (the reply carries the tailored content). Returns ``{ok,
    files:[{name, download_url}]}``. A ``BridgeParseError`` is a clean 400 with its
    message; a DOCX render failure is a 500."""
    data = request.get_json(silent=True) or {}
    reply = str(data.get("reply_text") or "")
    if not reply.strip():
        return jsonify({"ok": False, "error": "no reply text"}), 400
    from resume.service import data_from_paste, save_bundle_from_data
    try:
        parsed = data_from_paste(reply)
        resume_path, cover_path = save_bundle_from_data(
            parsed, workspace.output_dir())
    except BridgeParseError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except Exception as e:  # noqa: BLE001 — DOCX render failure
        return jsonify({"ok": False, "error": str(e)}), 500
    from pathlib import Path
    files = [{"name": Path(resume_path).name,
              "download_url": f"/api/resume/download/{Path(resume_path).name}"}]
    if cover_path:
        files.append({"name": Path(cover_path).name,
                      "download_url": f"/api/resume/download/{Path(cover_path).name}"})
    return jsonify({"ok": True, "files": files})


@resume_bp.get("/resume/download/<path:name>")
def resume_download(name: str):
    """Serve a generated resume/cover DOCX, LOCKED to the active project's output
    dir (traversal -> 404 via the shared downloads gate)."""
    return downloads.send_locked(_download_base(), name)
