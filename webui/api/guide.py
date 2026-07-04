"""Guide + backup/restore API (Phase 5).

Serves the static in-app Guide as structured JSON (from the Tk-free
``ui.help_core.GUIDE`` content), and re-hosts the tk Help-menu backup/restore over
HTTP: the tk flow reveals a saved zip in Explorer / picks one from a file dialog;
the web flow DOWNLOADS the backup zip and UPLOADS a zip to restore (repo rule: all
file handoffs are HTTP, server code never shells to explorer).

Backup safety (binding):
* Restore OVERWRITES user data, so it requires an explicit ``confirm=true`` (else
  400) AND — matching the safety the tk restore has via its dialog — takes a
  ``make_backup`` snapshot of the CURRENT data first, so a bad restore is
  recoverable (the tk flow warns + restarts; the web flow keeps a rollback zip).
* The uploaded zip is extracted through ``help_core.safe_extract_zip`` (ZIP-SLIP
  DEFENSE: every member's resolved path must stay inside the data root, symlink
  members refused, whole archive validated before any write) — never
  ``ZipFile.extractall``, which trusts member names. A hostile zip -> 400, nothing
  written outside the data folder.

Routes (mounted under ``/api``)
-------------------------------
* ``GET  /api/guide``            -> ``{ok, sections:[{heading, level, body}]}``  (read)
* ``GET  /api/backup/download``  -> the data-folder zip as an attachment          (read)
* ``POST /api/backup/restore``   -> restore from an uploaded zip (multipart)       [gate,
                                    requires ``confirm``; ZIP-SLIP safe]
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from flask import Blueprint, jsonify, request, send_file, after_this_request

from ..security import require_local_origin

guide_bp = Blueprint("webui_guide", __name__)


@guide_bp.get("/guide")
def guide():
    """The in-app Guide as structured sections for the web Guide page. Parsed from
    ``help_core.GUIDE`` via ``guide_sections()`` (each h1/h2 starts a section; the
    body text following it is joined). READ-only. Returns ``{ok, sections:[{heading,
    level, body}]}``."""
    from ui.help_core import guide_sections
    return jsonify({"ok": True, "sections": guide_sections()})


@guide_bp.get("/backup/download")
def backup_download():
    """Build a fresh backup zip of the data folder (``help_core.make_backup``,
    excluding backups/ + logs/) and stream it as a download attachment. READ-only
    (make_backup writes only to a temp path we then send + clean up). The zip is
    written into a per-request temp dir and removed after the response is sent, so
    no artifact lingers in the data folder. NOTE: the archive can contain a saved
    API key — the frontend warns the user not to share it (mirrors the tk copy)."""
    from ui.help_core import make_backup

    tmpdir = tempfile.mkdtemp(prefix="zag-backup-")
    try:
        zip_path = make_backup(str(Path(tmpdir) / "jobscout-backup"))
    except Exception as e:  # noqa: BLE001 — surface a build failure as 500
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)
        return jsonify({"ok": False, "error": str(e)}), 500

    @after_this_request
    def _cleanup(response):
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)
        return response

    return send_file(zip_path, as_attachment=True,
                     download_name="jobscout-backup.zip",
                     mimetype="application/zip")


def _truthy(v) -> bool:
    """Coerce a multipart form field or JSON value to a bool. A multipart field is
    always a string, so accept the usual truthy spellings ('true'/'1'/'yes'/'on')."""
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ("1", "true", "yes", "on")


@guide_bp.post("/backup/restore")
@require_local_origin
def backup_restore():
    """Restore the data folder from an UPLOADED backup zip (multipart form:
    ``file`` = the zip, ``confirm`` = true). DESTRUCTIVE (overwrites current data),
    so it is origin-gated AND requires ``confirm`` — an absent/false confirm is a
    400 with NOTHING written. Before extracting, a ``make_backup`` snapshot of the
    CURRENT data is taken (the recoverable-rollback safety the tk dialog provides
    via its warn-and-restart flow); its path is returned as ``rollback``.

    ZIP-SLIP SAFE: extraction goes through ``help_core.safe_extract_zip`` which
    validates every member's resolved path stays inside the data root and refuses
    symlink members — a hostile ``../../etc/x`` / absolute-path / symlink member
    raises before any write, surfaced here as a 400 (nothing extracted). Returns
    ``{ok, members:int, rollback:str}`` on success."""
    from ui.help_core import safe_extract_zip, make_backup, UnsafeZipEntry, backups_dir

    if not _truthy(request.form.get("confirm")):
        return jsonify({
            "ok": False,
            "error": "restore overwrites your data — resend with confirm=true",
        }), 400

    upload = request.files.get("file")
    if upload is None or not (upload.filename or "").strip():
        return jsonify({"ok": False, "error": "no backup file uploaded"}), 400

    import config
    dest = Path(config.USER_DATA_DIR)

    # Stage the upload to a temp file (never trust the client filename on disk).
    tmpdir = tempfile.mkdtemp(prefix="zag-restore-")
    try:
        staged = Path(tmpdir) / "upload.zip"
        upload.save(str(staged))

        # Snapshot current data first (rollback safety) — best-effort; a fresh
        # install with no data yet has nothing to snapshot.
        rollback = None
        try:
            if dest.exists() and any(dest.iterdir()):
                from datetime import datetime as _dt
                stamp = _dt.now().strftime("%Y%m%d_%H%M%S")
                rollback = make_backup(
                    str(backups_dir() / f"pre-restore-{stamp}"))
        except Exception:  # noqa: BLE001 — a snapshot hiccup never blocks restore
            rollback = None

        try:
            members = safe_extract_zip(str(staged), dest)
        except UnsafeZipEntry as e:
            return jsonify({"ok": False, "error": f"unsafe backup: {e}"}), 400
        except Exception as e:  # noqa: BLE001 — a corrupt zip is a clean 400
            return jsonify({"ok": False, "error": f"could not read backup: {e}"}), 400
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)

    return jsonify({"ok": True, "members": len(members), "rollback": rollback})
