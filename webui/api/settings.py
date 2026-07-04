"""Settings routes (Phase 0b: theme only).

Theme is persisted via ``ui.settings.set_theme`` — a zero-Tk module that writes
``ui_settings.json`` under the user data dir, reused verbatim by the web layer.
The PUT is origin-gated (it mutates persisted state) and validates the mode
against the known set; anything other than ``light``/``dark`` is a 400.

Source-key routes (masked GET / PUT / live-test) are Phase 1 — this module grows.
"""
from __future__ import annotations

from flask import Blueprint, request, jsonify

from ui import settings as ui_settings
from ..security import require_local_origin

settings_bp = Blueprint("webui_settings", __name__)

_VALID_THEMES = ("light", "dark")


@settings_bp.get("/settings/theme")
def get_theme():
    return jsonify({"ok": True, "mode": ui_settings.get_theme()})


@settings_bp.put("/settings/theme")
@require_local_origin
def put_theme():
    data = request.get_json(force=True, silent=True) or {}
    mode = data.get("mode")
    if mode not in _VALID_THEMES:
        return jsonify({"ok": False, "error": "invalid theme"}), 400
    ui_settings.set_theme(mode)
    return jsonify({"ok": True, "mode": ui_settings.get_theme()})
