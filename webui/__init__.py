"""Web-UI package: mounts the JSON API + built frontend onto the receiver's Flask
app.

``register_webui(app)`` is the single integration point ``scrape.browser_receiver``
calls (guarded by try/except ImportError, so the receiver stays functional
standalone if this package is absent). It:

* registers the ``/api`` blueprint (system/toppicks/settings/runs in Phase 0b);
* adds the static routes ``GET /app`` and ``GET /app/<path:p>`` serving the built
  frontend from :func:`paths.static_dir` with SPA fallback to ``index.html``.

Graceful degradation (Phase 0b): the frontend isn't built yet, so
:func:`paths.static_available` is False and the ``/app*`` routes answer 503
``{ok:false, error:"web UI not built"}`` instead of 404-ing on a missing dir.

Idempotent: a second call is a no-op (guarded by an attribute flag on the app),
so ``start_in_thread`` re-imports or a double registration can't double-register
blueprints (Flask raises on a duplicate blueprint name otherwise).
"""
from __future__ import annotations

from flask import jsonify, send_from_directory, abort

from . import paths
from .api import build_api_blueprint

_REGISTERED_FLAG = "_webui_registered"


def _serve_static(subpath: str = ""):
    """Serve a built frontend file, falling back to index.html for SPA client
    routes. 503 when the frontend isn't built (Phase 0b)."""
    if not paths.static_available():
        return jsonify({"ok": False, "error": "web UI not built"}), 503
    root = paths.static_dir()
    # An explicit asset request (has an extension / a real file) is served
    # directly; anything else is an SPA route -> index.html. send_from_directory
    # rejects path traversal (".." / absolute) safely.
    if subpath and (root / subpath).is_file():
        return send_from_directory(str(root), subpath)
    return send_from_directory(str(root), "index.html")


def register_webui(app) -> None:
    """Mount the API + static frontend onto ``app``. Idempotent."""
    if getattr(app, _REGISTERED_FLAG, False):
        return

    app.register_blueprint(build_api_blueprint())

    @app.get("/app")
    def _app_index():
        return _serve_static("")

    @app.get("/app/<path:p>")
    def _app_asset(p):
        return _serve_static(p)

    setattr(app, _REGISTERED_FLAG, True)
