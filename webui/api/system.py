"""System routes: app status, project list + active-project switch.

The project switch is the one route here that mutates process-wide state
(``workspace.set_active`` rewrites projects.json ``active``). It is origin-gated
and validated against the known project list before it touches the registry, so
an unknown slug is a clean 400 rather than a corrupt active pin.
"""
from __future__ import annotations

from flask import Blueprint, request, jsonify

import workspace
from ..security import require_local_origin

system_bp = Blueprint("webui_system", __name__)


def _theme() -> str:
    """The persisted theme, defaulting to 'light'. Isolated so a broken
    ui_settings import can't take out /api/status."""
    try:
        from ui import settings
        return settings.get_theme()
    except Exception:
        return "light"


def _version() -> str:
    try:
        import config
        return getattr(config, "APP_VERSION", "") or ""
    except Exception:
        return ""


def _project_summary(p: dict) -> dict:
    """The registry fields the UI needs per project."""
    return {
        "slug": p.get("slug", ""),
        "name": p.get("name", "") or p.get("slug", ""),
        "person": p.get("person"),
        "daily": bool(p.get("daily", False)),
    }


@system_bp.get("/status")
def status():
    return jsonify({
        "ok": True,
        "version": _version(),
        "project": workspace.active_slug(),
        "theme": _theme(),
    })


@system_bp.get("/project")
def project_list():
    projects = [_project_summary(p) for p in workspace.list_projects()]
    return jsonify({
        "ok": True,
        "active": workspace.active_slug(),
        "projects": projects,
    })


@system_bp.post("/project")
@require_local_origin
def project_switch():
    data = request.get_json(force=True, silent=True) or {}
    slug = data.get("slug")
    known = {p.get("slug") for p in workspace.list_projects()}
    if not slug or slug not in known:
        return jsonify({"ok": False, "error": "unknown project"}), 400
    workspace.set_active(slug)
    return jsonify({"ok": True, "active": workspace.active_slug()})
