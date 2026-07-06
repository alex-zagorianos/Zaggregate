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

from flask import jsonify, request, send_from_directory
from werkzeug.exceptions import HTTPException, NotFound

from . import paths
from .api import build_api_blueprint

_REGISTERED_FLAG = "_webui_registered"


def _api_http_error(e: HTTPException):
    """App-wide HTTP-error hook that keeps the ``{ok:false, error}`` JSON envelope
    on EVERY ``/api/*`` response, including errors raised at the ROUTING layer
    before any view runs (unknown route -> 404, wrong method -> 405, a literal
    ``../`` in a download path that werkzeug normalizes-and-404s, an oversized
    body -> 413). Views that already return their own JSON errors never reach
    this handler. Non-API paths (``/app`` SPA assets, receiver routes) return the
    exception unchanged — Flask then renders its default page, so only the API
    surface changes shape. (S36 scenario finding MINOR-2.)"""
    if request.path.startswith("/api/"):
        return jsonify({"ok": False,
                        "error": (e.name or "error").lower()}), e.code or 500
    return e


def _looks_like_spa_route(subpath: str) -> bool:
    """True when ``subpath`` is a client-side SPA route rather than an asset
    request: an asset's final path segment has a file extension (``app.js``,
    ``assets/main.css``); a SPA route does not (``inbox/some/deep/route``)."""
    last = subpath.rsplit("/", 1)[-1]
    return "." not in last


_ASSET_MAX_AGE = 31536000  # 1 year — Vite content-hashes asset filenames


def _no_cache_index(resp):
    """index.html changes across every build without a filename change, so it
    must always be revalidated — never long-cached like the hashed assets it
    references."""
    resp.headers["Cache-Control"] = "no-cache"
    return resp


def _serve_static(subpath: str = ""):
    """Serve a built frontend file, falling back to index.html for SPA client
    routes. 503 when the frontend isn't built (Phase 0b).

    ``send_from_directory`` is the SINGLE path-safety authority: it resolves the
    request against the static root and rejects traversal (``..``, absolute paths,
    encoded separators) by raising werkzeug ``NotFound``. We do NOT pre-check
    ``is_file`` ourselves — that would be a second, divergent traversal gate. On a
    miss we serve index.html for a SPA route (no extension in the final segment) or
    404 for a genuine missing asset.

    Cache headers: Vite's built assets (``app.js``, ``assets/main.css``, ...) are
    content-hashed, so a given filename's bytes never change — safe to cache for a
    year with ``immutable``. ``index.html`` (and the bare ``/app`` route, which
    serves it) is the one file whose CONTENT changes across a rebuild without a
    filename change, so it is explicitly marked ``no-cache`` (always revalidate)
    regardless of which branch below produced it — including the SPA fallback
    branch, which also serves index.html bytes for an unmatched client route.
    """
    if not paths.static_available():
        return jsonify({"ok": False, "error": "web UI not built"}), 503
    root = str(paths.static_dir())
    if not subpath:
        return _no_cache_index(send_from_directory(root, "index.html"))
    try:
        resp = send_from_directory(root, subpath, max_age=_ASSET_MAX_AGE)
        # send_file's max_age sets Cache-Control: max-age=<n>; Flask's send_file
        # has no `immutable` kwarg (Flask 3.x), so the `immutable` directive is
        # appended by hand — content-hashed filenames never change, so the
        # browser never needs to revalidate this response at all.
        resp.headers["Cache-Control"] = (
            f"{resp.headers.get('Cache-Control', f'max-age={_ASSET_MAX_AGE}')}, immutable"
        )
        return resp
    except NotFound:
        if _looks_like_spa_route(subpath):
            return _no_cache_index(send_from_directory(root, "index.html"))
        raise


def register_webui(app) -> None:
    """Mount the API + static frontend onto ``app``. Idempotent."""
    if getattr(app, _REGISTERED_FLAG, False):
        return

    app.register_blueprint(build_api_blueprint())
    app.register_error_handler(HTTPException, _api_http_error)

    @app.get("/app")
    def _app_index():
        return _serve_static("")

    @app.get("/app/<path:p>")
    def _app_asset(p):
        return _serve_static(p)

    setattr(app, _REGISTERED_FLAG, True)
