"""API blueprint assembly.

``build_api_blueprint()`` returns a single Flask ``Blueprint`` mounted at
``/api`` that registers every route submodule as a nested blueprint. Each phase
adds a submodule here (system/toppicks/settings/runs shipped in Phase 0b; inbox,
applications, prefs, resume, onboarding follow).
"""
from __future__ import annotations

from flask import Blueprint


def build_api_blueprint() -> Blueprint:
    api = Blueprint("webui_api", __name__, url_prefix="/api")

    from .system import system_bp
    from .toppicks import toppicks_bp
    from .settings import settings_bp
    from .runs import runs_bp

    # Nested blueprints inherit the /api prefix; each submodule declares its own
    # leaf paths (e.g. /status, /toppicks, /settings/theme, /jobs/<id>).
    api.register_blueprint(system_bp)
    api.register_blueprint(toppicks_bp)
    api.register_blueprint(settings_bp)
    api.register_blueprint(runs_bp)
    return api
