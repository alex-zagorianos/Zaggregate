"""Static-asset path resolution for the web UI, PyInstaller-aware.

The built frontend lives at ``webui/static/`` in source, and is bundled into the
frozen exe under ``<_MEIPASS>/webui/static`` (app.spec's ``datas`` — Phase 0d).
``static_dir()`` resolves the right one at runtime so the same ``register_webui``
code serves ``/app`` in dev AND in the packaged exe.

Phase 0b ships this before the frontend exists: ``static_available()`` lets the
static routes degrade gracefully (503 "web UI not built") until Phase 0c lands
``webui/static/``.
"""
from __future__ import annotations

import sys
from pathlib import Path


def static_dir() -> Path:
    """The directory the built frontend assets live in.

    Frozen (PyInstaller): ``<_MEIPASS>/webui/static`` — the bundle root the spec
    copies ``webui/static`` into. Dev: ``<this file's dir>/static`` i.e.
    ``<repo>/webui/static``. Returns a Path that may not exist yet (Phase 0b) —
    callers gate on :func:`static_available`.
    """
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass) / "webui" / "static"
    return Path(__file__).resolve().parent / "static"


def static_available() -> bool:
    """True once the built frontend exists (an ``index.html`` under
    :func:`static_dir`). False in Phase 0b / a source checkout that never ran the
    frontend build — the static routes then answer 503 instead of 404-ing on a
    missing directory."""
    d = static_dir()
    return d.is_dir() and (d / "index.html").is_file()
